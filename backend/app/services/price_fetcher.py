"""Download, decode and ingest official Israeli supermarket price data.

Israel's food-price transparency law (חוק קידום התחרות בענף המזון, 2014)
obliges every major retail chain to publish its full price list, keyed by
barcode. Two portals cover the leading chains:

* **Shufersal** publishes to a public Azure blob; the file index lives at
  ``prices.shufersal.co.il``. Listing hrefs are HTML-escaped and carry a SAS
  token, so they must be unescaped before use or the signature breaks.
* **Everyone else** uses the shared "Cerberus" portal at
  ``url.publishedprices.co.il``, which needs a per-chain username and an empty
  password. Its CSRF token must be re-read from the post-login page and sent
  as *both* a form field and the ``X-Csrftoken`` header.

Both portals serve the same government-mandated XML schema::

    Root/Items/Item -> ItemCode (barcode), ItemName, ManufactureName,
                       UnitOfMeasure, ItemPrice

Files are usually gzipped, but Azure may serve them already decompressed with
a UTF-8 BOM, so the decoder sniffs the gzip magic bytes instead of trusting the
``.gz`` extension.
"""

from __future__ import annotations

import gzip
import html
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterator, Sequence

import httpx

from app.supabase import supabase

logger = logging.getLogger(__name__)

SHUFERSAL_LISTING = "https://prices.shufersal.co.il/FileObject/UpdateCategory"
SHUFERSAL_PRICE_FULL_CATEGORY = 2
CERBERUS_BASE = "https://url.publishedprices.co.il"
USER_AGENT = "the-right-basket/0.1 (price transparency ingest)"
REQUEST_TIMEOUT = httpx.Timeout(30.0, read=180.0)

_CSRF_RE = re.compile(r'<meta name="csrftoken" content="([^"]+)"')
_BLOB_HREF_RE = re.compile(
    r'href="(https://pricesprodpublic\.blob\.core\.windows\.net/[^"]+)"'
)


@dataclass(frozen=True)
class Chain:
    """A retail chain and the portal its price files come from."""

    code: str
    name: str
    portal: str  # "shufersal" | "cerberus"
    chain_id: str  # 13-digit chain identifier embedded in file names
    username: str | None = None  # Cerberus login (password is empty)


#: Chains verified to serve PriceFull files. Each entry was confirmed against
#: the live portal rather than taken from documentation.
CHAINS: dict[str, Chain] = {
    c.code: c
    for c in (
        Chain("shufersal", "שופרסל", "shufersal", "7290027600007"),
        Chain("rami_levy", "רמי לוי", "cerberus", "7290058140886", "RamiLevi"),
        Chain("yohananof", "יוחננוף", "cerberus", "7290803800003", "yohananof"),
        Chain("osher_ad", "אושר עד", "cerberus", "7290103152017", "osherad"),
        Chain("tiv_taam", "טיב טעם", "cerberus", "7290873255550", "TivTaam"),
        Chain("dor_alon", "דור אלון", "cerberus", "7290492000005", "doralon"),
        Chain("keshet", "קשת טעמים", "cerberus", "7290055700007", "Keshet"),
        Chain("fresh_market", "פרש מרקט", "cerberus", "7290876100000", "freshmarket"),
        Chain("stop_market", "סטופ מרקט", "cerberus", "7290639000004", "Stop_Market"),
        Chain("salach_dabach", "סאלח דבאח", "cerberus", "7290526500006", "SalachD"),
        Chain("politzer", "פוליצר", "cerberus", "7291059100008", "politzer"),
    )
}


@dataclass(frozen=True)
class PriceRecord:
    """One product's price at one store, as published by the chain."""

    barcode: str
    name: str
    price: Decimal
    brand: str | None = None
    unit_of_measure: str | None = None
    store_id: str = ""


@dataclass(frozen=True)
class PriceFile:
    name: str
    url: str | None = None  # absolute (Shufersal); Cerberus builds it per-session


@dataclass
class SyncResult:
    """Outcome of a sync run, per chain and in total."""

    chains_synced: list[str] = field(default_factory=list)
    barcodes_requested: int = 0
    barcodes_found: int = 0
    products_upserted: int = 0
    prices_upserted: int = 0
    files_scanned: int = 0
    per_chain: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    duration_seconds: float = 0.0


def normalize_barcode(value: str | None) -> str:
    """Strip whitespace and leading zeros so lookups survive zero-padding."""
    cleaned = (value or "").strip()
    return cleaned.lstrip("0") or cleaned


def _decode(raw: bytes) -> str:
    """Decompress if gzipped, then decode, tolerating a UTF-8 BOM."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def _text(item: ET.Element, *tags: str) -> str:
    for tag in tags:
        value = item.findtext(tag)
        if value and value.strip():
            return value.strip()
    return ""


def parse_price_file(raw: bytes) -> Iterator[PriceRecord]:
    """Yield a :class:`PriceRecord` per priced item in one published file."""
    root = ET.fromstring(_decode(raw))
    store_id = _text(root, "StoreID", "StoreId")

    for item in root.iter():
        if item.tag not in ("Item", "Product"):
            continue
        barcode = _text(item, "ItemCode", "PriceCode")
        if not barcode:
            continue
        try:
            price = Decimal(_text(item, "ItemPrice", "Price") or "0")
        except InvalidOperation:
            continue
        if price <= 0:
            continue  # unpriced or delisted row
        brand = _text(item, "ManufactureName", "ManufacturerName")
        yield PriceRecord(
            barcode=barcode,
            name=_text(item, "ItemName", "ItemNm") or barcode,
            price=price,
            brand=None if brand in ("", "לא ידוע") else brand,
            unit_of_measure=_text(item, "UnitOfMeasure", "UnitQty") or None,
            store_id=store_id,
        )


class ShufersalPortal:
    """Public Azure-backed portal. No credentials required."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def list_price_files(self, limit: int) -> list[PriceFile]:
        files: list[PriceFile] = []
        page = 1
        while len(files) < limit and page <= 5:
            response = self._client.get(
                SHUFERSAL_LISTING,
                params={
                    "catID": SHUFERSAL_PRICE_FULL_CATEGORY,
                    "storeId": 0,
                    "page": page,
                },
            )
            response.raise_for_status()
            # Unescape &amp; or the SAS signature is corrupted and Azure 403s.
            urls = [html.unescape(u) for u in _BLOB_HREF_RE.findall(response.text)]
            if not urls:
                break
            for url in urls:
                name = url.split("/")[-1].split("?")[0]
                if name.startswith("PriceFull"):
                    files.append(PriceFile(name=name, url=url))
            page += 1
        return files[:limit]

    def download(self, price_file: PriceFile) -> bytes:
        assert price_file.url is not None
        response = self._client.get(price_file.url)
        response.raise_for_status()
        return response.content


class CerberusPortal:
    """Shared portal for most chains: username + empty password."""

    def __init__(self, client: httpx.Client, username: str) -> None:
        self._client = client
        self._username = username
        self._token: str | None = None

    def _login(self) -> None:
        page = self._client.get(f"{CERBERUS_BASE}/login")
        page.raise_for_status()
        match = _CSRF_RE.search(page.text)
        if match is None:
            raise RuntimeError("Cerberus login page has no CSRF token")
        self._client.post(
            f"{CERBERUS_BASE}/login/user",
            data={
                "username": self._username,
                "password": "",
                "csrftoken": match.group(1),
            },
        )
        # The token rotates on login; the pre-login one lists zero files.
        authed = self._client.get(f"{CERBERUS_BASE}/file")
        rotated = _CSRF_RE.search(authed.text)
        self._token = rotated.group(1) if rotated else match.group(1)

    def list_price_files(self, limit: int) -> list[PriceFile]:
        if self._token is None:
            self._login()
        response = self._client.post(
            f"{CERBERUS_BASE}/file/json/dir",
            data={
                "sEcho": "1",
                "iDisplayStart": "0",
                "iDisplayLength": "100000",
                "cd": "/",
                "csrftoken": self._token,
            },
            headers={
                "X-Csrftoken": self._token or "",
                "Referer": f"{CERBERUS_BASE}/file",
            },
        )
        response.raise_for_status()
        rows = response.json().get("aaData", [])
        names = sorted(
            (
                str(row["name"])
                for row in rows
                if str(row.get("name", "")).startswith("PriceFull")
            ),
            reverse=True,  # newest timestamp first
        )
        return [PriceFile(name=name) for name in names[:limit]]

    def download(self, price_file: PriceFile) -> bytes:
        response = self._client.get(f"{CERBERUS_BASE}/file/d/{price_file.name}")
        response.raise_for_status()
        return response.content


def _representative(records: Sequence[PriceRecord]) -> PriceRecord:
    """Collapse per-store rows into one chain-level price.

    Chains price most items uniformly, so the modal price across the sampled
    stores is the chain's shelf price. Ties break toward the cheaper value.
    """
    counts = Counter(record.price for record in records)
    chosen = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return next(record for record in records if record.price == chosen)


def fetch_chain_prices(
    chain: Chain,
    barcodes: Sequence[str] | None = None,
    max_files: int = 2,
    max_products: int = 50,
) -> tuple[dict[str, PriceRecord], int]:
    """Fetch one chain's prices, returning ``{normalized_barcode: record}``.

    When ``barcodes`` is empty the newest files are sampled instead and up to
    ``max_products`` items are returned, which seeds an empty database.
    """
    wanted = {normalize_barcode(b) for b in barcodes} if barcodes else None
    collected: dict[str, list[PriceRecord]] = {}
    files_scanned = 0

    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        portal: ShufersalPortal | CerberusPortal
        if chain.portal == "shufersal":
            portal = ShufersalPortal(client)
        elif chain.portal == "cerberus":
            if not chain.username:
                raise ValueError(f"chain {chain.code} has no Cerberus username")
            portal = CerberusPortal(client, chain.username)
        else:
            raise ValueError(f"unknown portal {chain.portal!r}")

        for price_file in portal.list_price_files(max_files):
            raw = portal.download(price_file)
            files_scanned += 1
            for record in parse_price_file(raw):
                key = normalize_barcode(record.barcode)
                if wanted is not None:
                    if key not in wanted:
                        continue
                elif key not in collected and len(collected) >= max_products:
                    continue
                collected.setdefault(key, []).append(record)
            if wanted is not None and wanted.issubset(collected):
                break  # every requested barcode found; stop early

    return {key: _representative(rows) for key, rows in collected.items()}, files_scanned


def _sync_chain_rows(chains: Sequence[Chain]) -> dict[str, str]:
    """Upsert chain rows, returning ``{chain_code: chain_uuid}``."""
    supabase.table("chains").upsert(
        [{"code": c.code, "name": c.name} for c in chains], on_conflict="code"
    ).execute()
    rows = (
        supabase.table("chains")
        .select("id,code")
        .in_("code", [c.code for c in chains])
        .execute()
        .data
    )
    return {row["code"]: row["id"] for row in rows}


def _sync_product_rows(records: Sequence[PriceRecord]) -> dict[str, str]:
    """Upsert product rows by barcode, returning ``{barcode: product_uuid}``."""
    by_barcode: dict[str, PriceRecord] = {}
    for record in records:
        by_barcode.setdefault(record.barcode, record)
    if not by_barcode:
        return {}

    supabase.table("products").upsert(
        [
            {
                "barcode": record.barcode,
                "name": record.name,
                "brand": record.brand,
                "unit_of_measure": record.unit_of_measure,
            }
            for record in by_barcode.values()
        ],
        on_conflict="barcode",
    ).execute()
    rows = (
        supabase.table("products")
        .select("id,barcode")
        .in_("barcode", list(by_barcode))
        .execute()
        .data
    )
    return {row["barcode"]: row["id"] for row in rows}


def sync_prices(
    barcodes: Sequence[str] | None = None,
    chain_codes: Sequence[str] | None = None,
    max_files_per_chain: int = 2,
    max_products: int = 50,
) -> SyncResult:
    """Scan the published files for the given chains and persist to Supabase.

    Each chain is fetched in its own thread; one chain failing (portal down,
    credentials rotated) is recorded in ``errors`` and does not abort the rest.
    """
    started = datetime.now(timezone.utc)
    selected = [CHAINS[code] for code in (chain_codes or CHAINS)]
    result = SyncResult(barcodes_requested=len(barcodes or []))

    fetched: dict[str, dict[str, PriceRecord]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(selected))) as pool:
        futures = {
            pool.submit(
                fetch_chain_prices, chain, barcodes, max_files_per_chain, max_products
            ): chain
            for chain in selected
        }
        for future in as_completed(futures):
            chain = futures[future]
            try:
                records, files_scanned = future.result()
            except Exception as exc:  # one chain must not sink the run
                logger.warning("chain %s failed: %s", chain.code, exc)
                result.errors[chain.code] = f"{type(exc).__name__}: {exc}"
                continue
            fetched[chain.code] = records
            result.files_scanned += files_scanned
            result.per_chain[chain.code] = len(records)
            result.chains_synced.append(chain.code)

    if not fetched:
        result.duration_seconds = (
            datetime.now(timezone.utc) - started
        ).total_seconds()
        return result

    chain_ids = _sync_chain_rows([CHAINS[code] for code in fetched])
    all_records = [r for records in fetched.values() for r in records.values()]
    product_ids = _sync_product_rows(all_records)
    result.products_upserted = len(product_ids)
    result.barcodes_found = len({normalize_barcode(r.barcode) for r in all_records})

    now = datetime.now(timezone.utc).isoformat()
    price_rows = [
        {
            "product_id": product_ids[record.barcode],
            "chain_id": chain_ids[chain_code],
            "price": float(record.price),
            # PriceFull carries shelf prices; promotions live in PromoFull,
            # which this module does not ingest yet.
            "is_discount": False,
            "updated_at": now,
        }
        for chain_code, records in fetched.items()
        for record in records.values()
        if record.barcode in product_ids and chain_code in chain_ids
    ]
    if price_rows:
        supabase.table("store_prices").upsert(
            price_rows, on_conflict="product_id,chain_id"
        ).execute()
        result.prices_upserted = len(price_rows)

    result.duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
    return result

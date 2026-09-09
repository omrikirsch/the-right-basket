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

Scanning at full scale
----------------------
A *full* scan means every store of every chain, which is roughly 900 files and
~10 GB of decompressed XML, so three properties of the portals drive the
design here:

* **One file already holds a whole catalogue.** ``PriceFull`` is a per-store
  snapshot of ~13k priced items, and chains republish the same store several
  times a day. Full coverage therefore means *the newest file per store*
  (:func:`_latest_per_store`); scanning older revisions of a store adds
  downloads but no products, so they are skipped.
* **Shufersal's index repeats itself.** Its pages overlap and it never serves
  an empty page, so listing stops when a page contributes no new file name
  rather than when a page comes back empty.
* **Parsing dominates the clock.** Files are streamed with ``iterparse`` and
  folded straight into per-barcode aggregates, so memory stays flat no matter
  how many files a chain publishes.
"""

from __future__ import annotations

import gzip
import html
import io
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator, Sequence

import httpx

from app.supabase import supabase

logger = logging.getLogger(__name__)

SHUFERSAL_LISTING = "https://prices.shufersal.co.il/FileObject/UpdateCategory"
SHUFERSAL_PRICE_FULL_CATEGORY = 2
CERBERUS_BASE = "https://url.publishedprices.co.il"
USER_AGENT = "the-right-basket/0.1 (price transparency ingest)"
REQUEST_TIMEOUT = httpx.Timeout(30.0, read=180.0)

#: Hard stop for Shufersal's self-repeating index. Its ~423 stores arrive 20
#: per page, so this leaves generous headroom while bounding a runaway loop.
MAX_LISTING_PAGES = 400
#: Shufersal's index is walked this many pages at a time; a whole batch
#: yielding no new name is what marks the end of the index.
LISTING_BATCH_PAGES = 12
#: Concurrent downloads within one chain, and chains scanned at once. The
#: product of the two is the load placed on the portals, so keep it modest.
DOWNLOAD_WORKERS = 6
CHAIN_WORKERS = 4
#: Supabase rejects very large request bodies, so writes go out in batches.
UPSERT_CHUNK = 500
#: ``in_`` filters travel in the query string, which has a length limit.
SELECT_CHUNK = 200

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
    """A published file, split into the store it covers and when it was cut.

    Published names look like
    ``PriceFull7290058140886-001-001-20260909-001008.gz``: chain id, then the
    store's sub-chain/branch segments, then the publication date and time.
    Some chains omit the sub-chain or fuse date and time, so the trailing
    timestamp is identified by segment length rather than by position.
    """

    name: str
    url: str | None = None  # absolute (Shufersal); Cerberus builds it per-session
    store_key: str = ""
    stamp: str = ""

    @classmethod
    def parse(cls, name: str, url: str | None = None) -> "PriceFile":
        parts = name.split(".", 1)[0].split("-")
        stamp: list[str] = []
        # A trailing HHMM/HHMMSS time, then the YYYYMMDD date (or a fused
        # YYYYMMDDHHMM). Store segments are shorter, so they are left alone.
        if len(parts) > 2 and parts[-1].isdigit() and len(parts[-1]) in (4, 6):
            stamp.insert(0, parts.pop())
        if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) in (8, 12, 14):
            stamp.insert(0, parts.pop())
        return cls(
            name=name,
            url=url,
            store_key="-".join(parts[1:]) or parts[0],
            stamp="".join(stamp),
        )


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
    per_chain_files: dict[str, int] = field(default_factory=dict)
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


def _chunks(values: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def parse_price_file(raw: bytes) -> Iterator[PriceRecord]:
    """Yield a :class:`PriceRecord` per priced item in one published file.

    Streams the document and discards each item once read: a store file is
    ~11 MB of XML, and a full scan holds several in flight at once.
    """
    store_id = ""
    for _, element in ET.iterparse(io.StringIO(_decode(raw)), events=("end",)):
        if element.tag in ("StoreID", "StoreId"):
            if not store_id:
                store_id = (element.text or "").strip()
            continue
        if element.tag not in ("Item", "Product"):
            continue

        barcode = _text(element, "ItemCode", "PriceCode")
        raw_price = _text(element, "ItemPrice", "Price")
        name = _text(element, "ItemName", "ItemNm")
        brand = _text(element, "ManufactureName", "ManufacturerName")
        unit = _text(element, "UnitOfMeasure", "UnitQty")
        element.clear()  # release the item's children before moving on

        if not barcode:
            continue
        try:
            price = Decimal(raw_price or "0")
        except InvalidOperation:
            continue
        if price <= 0:
            continue  # unpriced or delisted row
        yield PriceRecord(
            barcode=barcode,
            name=name or barcode,
            price=price,
            brand=None if brand in ("", "לא ידוע") else brand,
            unit_of_measure=unit or None,
            store_id=store_id,
        )


def _latest_per_store(files: Iterable[PriceFile]) -> list[PriceFile]:
    """Keep each store's newest file, newest store first.

    Chains republish a store several times a day and leave months of older
    revisions in the index; every one of them carries the same catalogue, so
    only the freshest is worth downloading.
    """
    newest: dict[str, PriceFile] = {}
    for price_file in files:
        current = newest.get(price_file.store_key)
        if current is None or price_file.stamp > current.stamp:
            newest[price_file.store_key] = price_file
    return sorted(newest.values(), key=lambda f: (f.stamp, f.name), reverse=True)


class ShufersalPortal:
    """Public Azure-backed portal. No credentials required."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def _page(self, page: int) -> list[tuple[str, str]]:
        """Return ``(file_name, signed_url)`` for one page of the index."""
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
        return [(url.split("/")[-1].split("?")[0], url) for url in urls]

    def list_price_files(self, limit: int | None) -> list[PriceFile]:
        """List PriceFull files, walking the index until it stops giving more.

        The index has one quirk that dictates the loop: its pages overlap, and
        once past the end the portal keeps re-serving the final page instead of
        an empty one. So exhaustion is detected by a batch of pages that adds
        no new file name, not by an empty response. Pages are fetched a batch
        at a time because there are ~215 of them at 20 files each.
        """
        seen: dict[str, PriceFile] = {}
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            for start in range(1, MAX_LISTING_PAGES + 1, LISTING_BATCH_PAGES):
                batch = range(start, start + LISTING_BATCH_PAGES)
                added = 0
                empty = True
                for entries in pool.map(self._page, batch):
                    if entries:
                        empty = False
                    for name, url in entries:
                        if name.startswith("PriceFull") and name not in seen:
                            seen[name] = PriceFile.parse(name, url)
                            added += 1
                if empty or added == 0:
                    break
                if limit is not None and len(seen) >= limit:
                    break

        files = _latest_per_store(seen.values())
        return files if limit is None else files[:limit]

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

    def list_price_files(self, limit: int | None) -> list[PriceFile]:
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
        files = _latest_per_store(
            PriceFile.parse(str(row["name"]))
            for row in rows
            if str(row.get("name", "")).startswith("PriceFull")
        )
        return files if limit is None else files[:limit]

    def download(self, price_file: PriceFile) -> bytes:
        response = self._client.get(f"{CERBERUS_BASE}/file/d/{price_file.name}")
        response.raise_for_status()
        return response.content


@dataclass
class _Aggregate:
    """Running per-barcode tally across every store file of one chain.

    Only the price histogram is kept rather than each store's row, so a chain
    with hundreds of stores costs the same memory as one with two.
    """

    name: str
    brand: str | None
    unit_of_measure: str | None
    barcode: str
    prices: Counter = field(default_factory=Counter)

    def add(self, record: PriceRecord) -> None:
        self.prices[record.price] += 1
        # Later files fill in details an earlier store left blank.
        if self.brand is None and record.brand:
            self.brand = record.brand
        if self.unit_of_measure is None and record.unit_of_measure:
            self.unit_of_measure = record.unit_of_measure

    def representative(self) -> PriceRecord:
        """Collapse per-store rows into one chain-level price.

        Chains price most items uniformly, so the modal price across the
        chain's stores is its shelf price. Ties break toward the cheaper value.
        """
        price = min(self.prices.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        return PriceRecord(
            barcode=self.barcode,
            name=self.name,
            price=price,
            brand=self.brand,
            unit_of_measure=self.unit_of_measure,
        )


def fetch_chain_prices(
    chain: Chain,
    barcodes: Sequence[str] | None = None,
    max_files: int | None = None,
    max_products: int | None = None,
) -> tuple[dict[str, PriceRecord], int]:
    """Fetch one chain's prices, returning ``{normalized_barcode: record}``.

    ``max_files`` and ``max_products`` are optional caps for quick sampling
    runs; left as ``None`` the scan is exhaustive, covering every store the
    chain publishes and every priced item in those files.

    When ``barcodes`` is empty the whole catalogue is ingested, which seeds an
    empty database; when it is given, scanning stops as soon as every
    requested barcode has been seen.
    """
    wanted = {normalize_barcode(b) for b in barcodes} if barcodes else None
    collected: dict[str, _Aggregate] = {}
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

        files = portal.list_price_files(max_files)
        logger.info("chain %s: scanning %d store files", chain.code, len(files))

        # Downloads are the slow part and parsing holds the GIL, so files are
        # fetched concurrently and folded in as they land.
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            futures = {
                pool.submit(portal.download, price_file): price_file
                for price_file in files
            }
            try:
                for future in as_completed(futures):
                    price_file = futures[future]
                    try:
                        raw = future.result()
                    except Exception as exc:  # a dead store file, not a dead chain
                        logger.warning(
                            "chain %s: %s failed: %s", chain.code, price_file.name, exc
                        )
                        continue

                    files_scanned += 1
                    for record in parse_price_file(raw):
                        key = normalize_barcode(record.barcode)
                        existing = collected.get(key)
                        if existing is not None:
                            existing.add(record)
                            continue
                        if wanted is not None and key not in wanted:
                            continue
                        if (
                            wanted is None
                            and max_products is not None
                            and len(collected) >= max_products
                        ):
                            continue
                        aggregate = _Aggregate(
                            name=record.name,
                            brand=record.brand,
                            unit_of_measure=record.unit_of_measure,
                            barcode=record.barcode,
                        )
                        aggregate.add(record)
                        collected[key] = aggregate

                    if files_scanned % 25 == 0:
                        logger.info(
                            "chain %s: %d/%d files, %d products",
                            chain.code,
                            files_scanned,
                            len(files),
                            len(collected),
                        )
                    if wanted is not None and wanted.issubset(collected):
                        break  # every requested barcode found; stop early
            finally:
                for future in futures:
                    future.cancel()

    logger.info(
        "chain %s: done, %d files, %d products",
        chain.code,
        files_scanned,
        len(collected),
    )
    return {key: agg.representative() for key, agg in collected.items()}, files_scanned


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
    """Upsert product rows by barcode, returning ``{barcode: product_uuid}``.

    A full scan carries six figures of barcodes, so rows are written in
    batches and the ids are taken from what each upsert returns instead of
    reading them back.
    """
    by_barcode: dict[str, PriceRecord] = {}
    for record in records:
        by_barcode.setdefault(record.barcode, record)
    if not by_barcode:
        return {}

    payload = [
        {
            "barcode": record.barcode,
            "name": record.name,
            "brand": record.brand,
            "unit_of_measure": record.unit_of_measure,
        }
        for record in by_barcode.values()
    ]

    product_ids: dict[str, str] = {}
    for index, chunk in enumerate(_chunks(payload, UPSERT_CHUNK), start=1):
        response = (
            supabase.table("products")
            .upsert(chunk, on_conflict="barcode")
            .execute()
        )
        for row in response.data or []:
            product_ids[row["barcode"]] = row["id"]
        logger.info(
            "products: upserted %d/%d", min(index * UPSERT_CHUNK, len(payload)),
            len(payload),
        )

    # Older PostgREST builds can answer an upsert without a representation;
    # fall back to reading back only the ids that are still missing.
    missing = [barcode for barcode in by_barcode if barcode not in product_ids]
    for chunk in _chunks(missing, SELECT_CHUNK):
        rows = (
            supabase.table("products")
            .select("id,barcode")
            .in_("barcode", list(chunk))
            .execute()
            .data
        )
        for row in rows:
            product_ids[row["barcode"]] = row["id"]
    return product_ids


def sync_prices(
    barcodes: Sequence[str] | None = None,
    chain_codes: Sequence[str] | None = None,
    max_files_per_chain: int | None = None,
    max_products: int | None = None,
) -> SyncResult:
    """Scan the published files for the given chains and persist to Supabase.

    With the caps left at ``None`` this is a full scan: every store file each
    chain publishes, and every priced item within them.

    Each chain is fetched in its own thread; one chain failing (portal down,
    credentials rotated) is recorded in ``errors`` and does not abort the rest.
    """
    started = datetime.now(timezone.utc)
    selected = [CHAINS[code] for code in (chain_codes or CHAINS)]
    result = SyncResult(barcodes_requested=len(barcodes or []))

    fetched: dict[str, dict[str, PriceRecord]] = {}
    with ThreadPoolExecutor(max_workers=min(CHAIN_WORKERS, len(selected))) as pool:
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
            result.per_chain_files[chain.code] = files_scanned
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
    # Keyed so a barcode that appears twice for one chain cannot produce two
    # conflicting rows in the same statement, which Postgres refuses.
    price_rows: dict[tuple[str, str], dict] = {
        (product_ids[record.barcode], chain_ids[chain_code]): {
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
    }
    rows = list(price_rows.values())
    for index, chunk in enumerate(_chunks(rows, UPSERT_CHUNK), start=1):
        supabase.table("store_prices").upsert(
            list(chunk), on_conflict="product_id,chain_id"
        ).execute()
        result.prices_upserted += len(chunk)
        logger.info("store_prices: upserted %d/%d", result.prices_upserted, len(rows))

    result.duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
    return result

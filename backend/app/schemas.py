"""Request and response models for the public API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SyncPricesRequest(BaseModel):
    """Which products and chains to scan, and how far to go.

    Every field defaults to "everything": an empty body runs a full scan of
    each chain's whole catalogue across all of its stores. The two caps exist
    for quick sampling runs and are off unless set.
    """

    barcodes: list[str] = Field(default_factory=list, max_length=200)
    chains: list[str] = Field(
        default_factory=list, description="Chain codes; empty means every chain."
    )
    max_files_per_chain: int | None = Field(
        None,
        ge=1,
        description="Cap on store files per chain; omit to scan every store.",
    )
    max_products: int | None = Field(
        None,
        ge=1,
        description="Cap on products per chain; omit to ingest the full catalogue.",
    )


class SyncPricesResponse(BaseModel):
    chains_synced: list[str]
    barcodes_requested: int
    barcodes_found: int
    products_upserted: int
    prices_upserted: int
    files_scanned: int
    per_chain: dict[str, int]
    per_chain_files: dict[str, int]
    errors: dict[str, str]
    duration_seconds: float


class ChainPrice(BaseModel):
    chain_code: str
    chain_name: str
    price: float
    is_discount: bool
    updated_at: datetime | None = None


class Product(BaseModel):
    id: str
    barcode: str
    name: str
    brand: str | None = None
    unit_of_measure: str | None = None
    prices: list[ChainPrice] = Field(default_factory=list)
    min_price: float | None = None
    max_price: float | None = None
    cheapest_chain: str | None = None


class ProductList(BaseModel):
    count: int
    limit: int
    offset: int
    products: list[Product]


class ChainInfo(BaseModel):
    code: str
    name: str
    portal: str

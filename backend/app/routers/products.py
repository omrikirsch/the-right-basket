"""Endpoints that read ingested products and their per-chain prices."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ChainPrice, Product, ProductList
from app.supabase import supabase

router = APIRouter(prefix="/api", tags=["products"])

# One round trip: products with their prices and each price's chain.
_SELECT = (
    "id,barcode,name,brand,unit_of_measure,"
    "store_prices(price,is_discount,updated_at,chains(code,name))"
)


def _to_product(row: dict) -> Product:
    prices: list[ChainPrice] = []
    for entry in row.get("store_prices") or []:
        chain = entry.get("chains") or {}
        if entry.get("price") is None:
            continue
        prices.append(
            ChainPrice(
                chain_code=chain.get("code", ""),
                chain_name=chain.get("name", ""),
                price=float(entry["price"]),
                is_discount=bool(entry.get("is_discount")),
                updated_at=entry.get("updated_at"),
            )
        )
    prices.sort(key=lambda p: p.price)

    return Product(
        id=row["id"],
        barcode=row["barcode"],
        name=row["name"],
        brand=row.get("brand"),
        unit_of_measure=row.get("unit_of_measure"),
        prices=prices,
        min_price=prices[0].price if prices else None,
        max_price=prices[-1].price if prices else None,
        cheapest_chain=prices[0].chain_code if prices else None,
    )


@router.get("/products", response_model=ProductList)
def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    barcode: str | None = Query(None, description="Exact barcode match."),
    search: str | None = Query(None, min_length=2, description="Name contains."),
    priced_only: bool = Query(
        False, description="Only products that have at least one chain price."
    ),
) -> ProductList:
    """Real products ingested from the chains, with their price per chain."""
    query = supabase.table("products").select(_SELECT, count="exact")
    if barcode:
        query = query.eq("barcode", barcode)
    if search:
        query = query.ilike("name", f"%{search}%")

    try:
        response = (
            query.order("name").range(offset, offset + limit - 1).execute()
        )
    except Exception as exc:  # surface Supabase/PostgREST problems honestly
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")

    products = [_to_product(row) for row in response.data]
    if priced_only:
        products = [p for p in products if p.prices]

    return ProductList(
        count=response.count if response.count is not None else len(products),
        limit=limit,
        offset=offset,
        products=products,
    )

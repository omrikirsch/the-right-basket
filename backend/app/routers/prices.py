"""Endpoints that trigger ingestion of official price data."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ChainInfo, SyncPricesRequest, SyncPricesResponse
from app.services.price_fetcher import CHAINS, sync_prices

router = APIRouter(prefix="/api", tags=["prices"])


@router.get("/chains", response_model=list[ChainInfo])
def list_chains() -> list[ChainInfo]:
    """Chains this engine can scan, with the portal each one publishes to."""
    return [
        ChainInfo(code=c.code, name=c.name, portal=c.portal) for c in CHAINS.values()
    ]


@router.post("/sync-prices", response_model=SyncPricesResponse)
def sync_prices_endpoint(payload: SyncPricesRequest) -> SyncPricesResponse:
    """Scan the published price files and upsert the results into Supabase.

    Runs synchronously and hits external portals, so expect seconds per chain.
    A chain that fails is reported in ``errors`` rather than failing the call.
    """
    unknown = sorted(set(payload.chains) - set(CHAINS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unknown chain codes",
                "unknown": unknown,
                "valid": sorted(CHAINS),
            },
        )

    result = sync_prices(
        barcodes=payload.barcodes or None,
        chain_codes=payload.chains or None,
        max_files_per_chain=payload.max_files_per_chain,
        max_products=payload.max_products,
    )

    if not result.chains_synced and result.errors:
        raise HTTPException(
            status_code=502,
            detail={"message": "Every chain failed", "errors": result.errors},
        )

    return SyncPricesResponse(**vars(result))

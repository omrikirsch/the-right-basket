from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(
    title="The Right Basket API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthcheck", tags=["system"])
async def healthcheck() -> dict[str, str]:
    """Liveness probe used by the frontend and by deployment tooling."""
    return {
        "status": "ok",
        "service": "the-right-basket-backend",
        "version": app.version,
        "environment": settings.environment,
    }

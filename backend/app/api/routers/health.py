from fastapi import APIRouter, HTTPException

from app.core.database import database_is_ready


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    if not database_is_ready():
        raise HTTPException(
            status_code=503,
            detail="Servizio temporaneamente non disponibile.",
        )
    return {"status": "ok", "service": "logistica-operations"}

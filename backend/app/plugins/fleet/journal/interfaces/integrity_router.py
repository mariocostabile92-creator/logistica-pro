from fastapi import APIRouter, HTTPException, Request

from app.auth.permission_service import has_permission
from app.plugins.fleet.journal.application.integrity_service import report


router = APIRouter(prefix="/api/fleet/journal-integrity", tags=["fleet-journal-integrity"])


@router.get("")
def integrity(request: Request):
    if not has_permission(request.state.user.role, "journal:configure"):
        raise HTTPException(status_code=403, detail="Permesso insufficiente.")
    return report(request.state.user.organization_id)

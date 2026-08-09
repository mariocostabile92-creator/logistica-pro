from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth.permission_service import has_permission
from app.plugins.dsp_workspace.application.service import (
    daily_operations_snapshot,
)
from app.plugins.dsp_workspace.domain.models import DailyOperationsSnapshot


router = APIRouter(prefix="/api/dsp-workspace", tags=["dsp-workspace"])
SOURCE_PERMISSIONS = ("planning:read", "workforce:read", "fleet:read")


@router.get("/daily-snapshot", response_model=DailyOperationsSnapshot)
def get_daily_snapshot(
    request: Request,
    operation_date: date = Query(...),
) -> DailyOperationsSnapshot:
    user = request.state.user
    if not all(has_permission(user.role, item) for item in SOURCE_PERMISSIONS):
        raise HTTPException(status_code=403, detail="Permesso sorgente insufficiente.")
    return daily_operations_snapshot(
        operation_date=operation_date.isoformat(),
        organization_id=str(user.organization_id),
    )


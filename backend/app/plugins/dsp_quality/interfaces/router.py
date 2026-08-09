from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.auth.permission_service import has_permission
from app.core.config import MAX_UPLOAD_SIZE_BYTES
from app.plugins.dsp_quality.application.import_contract import QualitySourceInput
from app.plugins.dsp_quality.application.preview_models import (
    QualityImportAction,
    QualityImportConfirmation,
    QualityImportPreview,
)
from app.plugins.dsp_quality.application.preview_service import (
    QualityPreviewError,
    confirm_scorecard_import,
    preview_scorecard_import,
)
from app.plugins.dsp_quality.application.read_models import QualityLatestOverview
from app.plugins.dsp_quality.application.read_service import get_latest_scorecard


router = APIRouter(prefix="/api/dsp-quality", tags=["dsp-quality"])


def _require_import_permission(request: Request) -> None:
    if not has_permission(request.state.user.role, "admin:write"):
        raise HTTPException(
            status_code=403,
            detail="Permesso import Quality insufficiente.",
        )


def _require_read_permission(request: Request) -> None:
    if not has_permission(request.state.user.role, "admin:read"):
        raise HTTPException(
            status_code=403,
            detail="Permesso lettura Quality insufficiente.",
        )


async def _source(file: UploadFile) -> QualitySourceInput:
    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Il file supera la dimensione massima consentita.",
        )
    return QualitySourceInput(
        filename=file.filename or "scorecard.pdf",
        content=content,
        media_type=file.content_type,
    )


def _guard(call, **kwargs):
    try:
        return call(**kwargs)
    except QualityPreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/scorecards/latest", response_model=QualityLatestOverview)
def latest_scorecard(request: Request):
    _require_read_permission(request)
    return get_latest_scorecard(request.state.user.organization_id)


@router.post("/scorecards/preview", response_model=QualityImportPreview)
async def preview_scorecard(request: Request, file: UploadFile = File(...)):
    _require_import_permission(request)
    return _guard(
        preview_scorecard_import,
        organization_id=request.state.user.organization_id,
        source=await _source(file),
    )


@router.post("/scorecards/import", response_model=QualityImportConfirmation)
async def import_scorecard(
    request: Request,
    file: UploadFile = File(...),
    preview_token: str = Form(..., min_length=16),
    expected_action: QualityImportAction | None = Form(default=None),
):
    _require_import_permission(request)
    return _guard(
        confirm_scorecard_import,
        organization_id=request.state.user.organization_id,
        source=await _source(file),
        preview_token=preview_token,
        imported_by=request.state.user.id,
        expected_action=expected_action,
    )

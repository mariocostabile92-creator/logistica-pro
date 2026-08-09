from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

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
from app.plugins.dsp_quality.application.metrics_read_models import QualityLatestMetrics
from app.plugins.dsp_quality.application.metrics_read_service import get_latest_metrics
from app.plugins.dsp_quality.application.drivers_read_models import QualityLatestDrivers
from app.plugins.dsp_quality.application.drivers_read_service import get_latest_drivers
from app.plugins.dsp_quality.application.mapping_service import (
    MappingConflictError,
    MappingNotFoundError,
)
from app.plugins.dsp_quality.application.reconciliation_models import (
    MappingHistory,
    MappingRemoveRequest,
    MappingWriteRequest,
    MappingWriteResult,
    ReconciliationState,
    WorkforceCandidateList,
)
from app.plugins.dsp_quality.application.reconciliation_service import (
    ReconciliationNotFoundError,
    delete_mapping,
    mapping_history,
    put_mapping,
    reconciliation_state,
    search_workforce_candidates,
)


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


@router.get("/scorecards/latest/metrics", response_model=QualityLatestMetrics)
def latest_scorecard_metrics(request: Request):
    _require_read_permission(request)
    return get_latest_metrics(request.state.user.organization_id)


@router.get("/scorecards/latest/drivers", response_model=QualityLatestDrivers)
def latest_scorecard_drivers(request: Request):
    _require_read_permission(request)
    return get_latest_drivers(request.state.user.organization_id)


@router.get(
    "/transporter-mappings/reconciliation",
    response_model=ReconciliationState,
)
def transporter_mapping_reconciliation(request: Request):
    _require_read_permission(request)
    return reconciliation_state(request.state.user.organization_id)


@router.get(
    "/transporter-mappings/workforce-candidates",
    response_model=WorkforceCandidateList,
)
def transporter_mapping_candidates(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
):
    _require_read_permission(request)
    return search_workforce_candidates(
        request.state.user.organization_id,
        q,
        limit,
    )


def _mapping_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MappingConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (MappingNotFoundError, ReconciliationNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.put(
    "/transporter-mappings/{transporter_external_id}",
    response_model=MappingWriteResult,
)
def put_transporter_mapping(
    transporter_external_id: str,
    payload: MappingWriteRequest,
    request: Request,
):
    _require_import_permission(request)
    try:
        return put_mapping(
            organization_id=request.state.user.organization_id,
            external_id=transporter_external_id,
            workforce_member_id=payload.workforce_member_id,
            actor=request.state.user.id,
            expected_updated_at=(
                payload.expected_updated_at.isoformat()
                if payload.expected_updated_at else None
            ),
        )
    except (ValueError, ReconciliationNotFoundError) as exc:
        raise _mapping_error(exc) from exc


@router.delete(
    "/transporter-mappings/{transporter_external_id}",
    response_model=MappingWriteResult,
)
def delete_transporter_mapping(
    transporter_external_id: str,
    payload: MappingRemoveRequest,
    request: Request,
):
    _require_import_permission(request)
    try:
        return delete_mapping(
            organization_id=request.state.user.organization_id,
            external_id=transporter_external_id,
            actor=request.state.user.id,
            expected_updated_at=payload.expected_updated_at.isoformat(),
        )
    except (ValueError, ReconciliationNotFoundError) as exc:
        raise _mapping_error(exc) from exc


@router.get(
    "/transporter-mappings/{transporter_external_id}/history",
    response_model=MappingHistory,
)
def transporter_mapping_history(
    transporter_external_id: str,
    request: Request,
):
    _require_read_permission(request)
    try:
        return mapping_history(
            request.state.user.organization_id,
            transporter_external_id,
        )
    except ReconciliationNotFoundError as exc:
        raise _mapping_error(exc) from exc


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

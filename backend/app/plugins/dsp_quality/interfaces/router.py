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
from app.plugins.dsp_quality.application.read_service import get_latest_scorecard, get_scorecard
from app.plugins.dsp_quality.application.metrics_read_models import QualityLatestMetrics
from app.plugins.dsp_quality.application.metrics_read_service import get_latest_metrics, get_metrics
from app.plugins.dsp_quality.application.drivers_read_models import QualityLatestDrivers
from app.plugins.dsp_quality.application.drivers_read_service import get_latest_drivers, get_drivers
from app.plugins.dsp_quality.application.attention_read_models import QualityAttentionReadModel
from app.plugins.dsp_quality.application.attention_read_service import (
    get_attention,
    get_latest_attention,
)
from app.plugins.dsp_quality.application.driver_history_models import (
    QualityDriverHistoryReadModel,
)
from app.plugins.dsp_quality.application.driver_history_service import (
    get_driver_history,
)
from app.plugins.dsp_quality.application.followup_models import (
    QualityFollowupCloseRequest,
    QualityFollowupCreateRequest,
    QualityFollowupCreateResult,
    QualityFollowupList,
    QualityFollowupReadModel,
)
from app.plugins.dsp_quality.application.followup_service import (
    close_followup,
    create_followup,
    get_followup,
    list_followups,
)
from app.plugins.dsp_quality.application.history_models import QualityScorecardHistory
from app.plugins.dsp_quality.application.history_service import (
    ensure_scorecard,
    get_scorecard_history,
)
from app.plugins.dsp_quality.application.identity_source_models import (
    ExactIdentityApplyResult,
    IdentitySourcePreview,
)
from app.plugins.dsp_quality.application.identity_source_service import (
    IdentitySourceError,
    apply_exact_identity_matches,
    preview_identity_source,
)
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
from app.plugins.dsp_quality.infrastructure.adapters.tabular_identity_source import (
    IdentitySourceSelection,
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


async def _identity_source(file: UploadFile | None) -> QualitySourceInput | None:
    if file is None:
        return None
    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Il file supera la dimensione massima consentita.",
        )
    return QualitySourceInput(
        filename=file.filename or "identity-source.xlsx",
        content=content,
        media_type=file.content_type,
    )


def _guard(call, **kwargs):
    try:
        return call(**kwargs)
    except QualityPreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _identity_guard(call, **kwargs):
    try:
        return call(**kwargs)
    except IdentitySourceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/scorecards", response_model=QualityScorecardHistory)
def scorecard_history(request: Request):
    _require_read_permission(request)
    return get_scorecard_history(request.state.user.organization_id)


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


@router.get("/scorecards/latest/attention", response_model=QualityAttentionReadModel)
def latest_scorecard_attention(request: Request):
    _require_read_permission(request)
    return get_latest_attention(request.state.user.organization_id)


@router.get(
    "/drivers/{transporter_external_id}/history",
    response_model=QualityDriverHistoryReadModel,
)
def driver_quality_history(
    transporter_external_id: str,
    request: Request,
    scorecard_id: str | None = Query(default=None),
    limit: int = Query(default=52, ge=1, le=260),
):
    _require_read_permission(request)
    try:
        return get_driver_history(
            request.state.user.organization_id,
            transporter_external_id,
            scorecard_id=scorecard_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _followup_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/followups", response_model=QualityFollowupCreateResult)
def create_quality_followup(
    payload: QualityFollowupCreateRequest,
    request: Request,
):
    _require_import_permission(request)
    try:
        return create_followup(
            request.state.user.organization_id,
            payload,
            actor=request.state.user.id,
        )
    except (ValueError, LookupError, RuntimeError) as exc:
        raise _followup_error(exc) from exc


@router.get("/followups", response_model=QualityFollowupList)
def quality_followups(
    request: Request,
    status: str | None = Query(default=None),
    transporter_external_id: str | None = Query(default=None, max_length=180),
    metric_key: str | None = Query(default=None, max_length=180),
):
    _require_read_permission(request)
    try:
        return list_followups(
            request.state.user.organization_id,
            status=status,
            transporter_external_id=transporter_external_id,
            metric_key=metric_key,
        )
    except ValueError as exc:
        raise _followup_error(exc) from exc


@router.get("/followups/{followup_id}", response_model=QualityFollowupReadModel)
def quality_followup(followup_id: str, request: Request):
    _require_read_permission(request)
    try:
        return get_followup(request.state.user.organization_id, followup_id)
    except LookupError as exc:
        raise _followup_error(exc) from exc


@router.post(
    "/followups/{followup_id}/close",
    response_model=QualityFollowupReadModel,
)
def close_quality_followup(
    followup_id: str,
    payload: QualityFollowupCloseRequest,
    request: Request,
):
    _require_import_permission(request)
    try:
        return close_followup(
            request.state.user.organization_id,
            followup_id,
            actor=request.state.user.id,
            note=payload.note,
        )
    except (LookupError, RuntimeError) as exc:
        raise _followup_error(exc) from exc


@router.get("/scorecards/{scorecard_id}", response_model=QualityLatestOverview)
def selected_scorecard(scorecard_id: str, request: Request):
    _require_read_permission(request)
    try:
        ensure_scorecard(request.state.user.organization_id, scorecard_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_scorecard(request.state.user.organization_id, scorecard_id)


@router.get("/scorecards/{scorecard_id}/metrics", response_model=QualityLatestMetrics)
def selected_scorecard_metrics(scorecard_id: str, request: Request):
    _require_read_permission(request)
    try:
        ensure_scorecard(request.state.user.organization_id, scorecard_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_metrics(request.state.user.organization_id, scorecard_id)


@router.get("/scorecards/{scorecard_id}/drivers", response_model=QualityLatestDrivers)
def selected_scorecard_drivers(scorecard_id: str, request: Request):
    _require_read_permission(request)
    try:
        ensure_scorecard(request.state.user.organization_id, scorecard_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_drivers(request.state.user.organization_id, scorecard_id)


@router.get(
    "/scorecards/{scorecard_id}/attention",
    response_model=QualityAttentionReadModel,
)
def selected_scorecard_attention(scorecard_id: str, request: Request):
    _require_read_permission(request)
    try:
        ensure_scorecard(request.state.user.organization_id, scorecard_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_attention(request.state.user.organization_id, scorecard_id)


@router.get(
    "/transporter-mappings/reconciliation",
    response_model=ReconciliationState,
)
def transporter_mapping_reconciliation(
    request: Request,
    scorecard_id: str | None = Query(default=None),
):
    _require_read_permission(request)
    if scorecard_id:
        try:
            ensure_scorecard(request.state.user.organization_id, scorecard_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return reconciliation_state(request.state.user.organization_id, scorecard_id)


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


@router.post(
    "/transporter-mappings/source-preview",
    response_model=IdentitySourcePreview,
)
async def transporter_mapping_source_preview(
    request: Request,
    scorecard_id: str = Form(..., min_length=1),
    file: UploadFile | None = File(default=None),
    use_planning: bool = Form(default=False),
    sheet: str | None = Form(default=None),
    transporter_column: str | None = Form(default=None),
    driver_column: str | None = Form(default=None),
):
    _require_import_permission(request)
    return _identity_guard(
        preview_identity_source,
        organization_id=request.state.user.organization_id,
        scorecard_id=scorecard_id,
        source=await _identity_source(file),
        use_planning=use_planning,
        selection=IdentitySourceSelection(
            sheet=sheet,
            transporter_column=transporter_column,
            driver_column=driver_column,
        ),
    )


@router.post(
    "/transporter-mappings/source-apply-exact",
    response_model=ExactIdentityApplyResult,
)
async def transporter_mapping_source_apply_exact(
    request: Request,
    scorecard_id: str = Form(..., min_length=1),
    preview_token: str = Form(..., min_length=16),
    file: UploadFile | None = File(default=None),
    use_planning: bool = Form(default=False),
):
    _require_import_permission(request)
    return _identity_guard(
        apply_exact_identity_matches,
        organization_id=request.state.user.organization_id,
        scorecard_id=scorecard_id,
        actor=request.state.user.id,
        preview_token=preview_token,
        source=await _identity_source(file),
        use_planning=use_planning,
    )


def _mapping_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MappingConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (MappingNotFoundError, ReconciliationNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LookupError):
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
    scorecard_id: str | None = Query(default=None),
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
            scorecard_id=scorecard_id,
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
    scorecard_id: str | None = Query(default=None),
):
    _require_import_permission(request)
    try:
        return delete_mapping(
            organization_id=request.state.user.organization_id,
            external_id=transporter_external_id,
            actor=request.state.user.id,
            expected_updated_at=payload.expected_updated_at.isoformat(),
            scorecard_id=scorecard_id,
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
    scorecard_id: str | None = Query(default=None),
):
    _require_read_permission(request)
    try:
        return mapping_history(
            request.state.user.organization_id,
            transporter_external_id,
            scorecard_id,
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

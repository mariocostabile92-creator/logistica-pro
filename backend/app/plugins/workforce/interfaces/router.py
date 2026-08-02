from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile

from app.auth.permission_service import has_permission

from app.importers.excel_reader import validate_upload
from app.importers.workbook_profiler.errors import WorkbookProfileError
from app.plugins.workforce.application import workforce_service
from app.plugins.workforce.application import consecutivity_policy, override_service
from app.plugins.workforce.application.consecutivity_service import snapshots as consecutivity_snapshots
from app.plugins.workforce.application.foundation_service import foundation_snapshot
from app.plugins.workforce.domain.errors import (
    WorkforceImportError,
    WorkforceMemberNotFoundError,
    WorkforceStatusNotFoundError,
    WorkforceValidationError,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceImportPreview,
    WorkforceImportResult,
    WorkforceMember,
    WorkforceFoundationSnapshot,
)
from app.plugins.workforce.infrastructure import read_repository
from app.plugins.workforce.interfaces.schemas import (
    WorkforceCalendarResponse,
    WorkforceChangesResponse,
    WorkforceCoverageResponse,
    WorkforceDayStatusRequest,
    WorkforceMembersResponse,
    WorkforceMemberUpdateRequest,
    WorkforceStatusResponse,
    ConsecutivityOverrideRequest,
    ConsecutivityPolicyRequest,
)
from app.workspace.status_service import (
    DemoWorkspaceResetRequiredError,
    ensure_real_data_write_allowed,
)


router = APIRouter(
    prefix="/api/plugins/workforce/v1",
    tags=["workforce-plugin-v1"],
)


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read()
    validate_upload(file, content)
    return content, file.filename or "workforce-upload"


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DemoWorkspaceResetRequiredError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_WORKSPACE_RESET_REQUIRED",
                "message": str(exc),
            },
        )
    code = getattr(exc, "code", "WORKFORCE_VALIDATION_ERROR")
    return HTTPException(
        status_code=422,
        detail={"code": code, "message": str(exc)},
    )


def _require(request: Request, permission: str):
    user = request.state.user
    if not has_permission(user.role, permission):
        raise HTTPException(status_code=403, detail="Operazione Workforce non autorizzata.")
    return user


@router.get("/status", response_model=WorkforceStatusResponse)
def status(request: Request) -> WorkforceStatusResponse:
    user = _require(request, "workforce:read")
    members = workforce_service.list_members(user.organization_id)
    return WorkforceStatusResponse(
        member_count=len(members),
        latest_import=read_repository.latest_import_summary(),
    )


@router.get("/members", response_model=WorkforceMembersResponse)
def members(request: Request) -> WorkforceMembersResponse:
    user = _require(request, "workforce:read")
    return WorkforceMembersResponse(items=workforce_service.list_members(user.organization_id))


@router.get("/foundation", response_model=WorkforceFoundationSnapshot)
def foundation(
    request: Request,
    operation_date: str | None = Query(default=None),
) -> WorkforceFoundationSnapshot:
    try:
        user = _require(request, "workforce:read")
        snapshot = foundation_snapshot(operation_date, user.organization_id)
        snapshot.permissions = {
            "can_configure_policy": has_permission(user.role, "workforce:policy:write"),
            "can_override": has_permission(user.role, "workforce:override"),
        }
        return snapshot
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data operativa non valida.") from exc


@router.get("/consecutivity/policy")
def get_consecutivity_policy(request: Request):
    user = _require(request, "workforce:read")
    return consecutivity_policy.policy(user.organization_id)


@router.put("/consecutivity/policy")
def put_consecutivity_policy(payload: ConsecutivityPolicyRequest, request: Request):
    user = _require(request, "workforce:policy:write")
    try:
        return consecutivity_policy.update_policy(
            user.organization_id, **payload.model_dump(), actor=user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/consecutivity/overrides", status_code=201)
def create_consecutivity_override(payload: ConsecutivityOverrideRequest, request: Request):
    user = _require(request, "workforce:override")
    try:
        return override_service.create_override(
            user.organization_id, **payload.model_dump(), actor=user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/consecutivity/{member_id}")
def member_consecutivity(
    member_id: int,
    request: Request,
    operation_date: str | None = Query(default=None),
):
    user = _require(request, "workforce:read")
    target = operation_date or date.today().isoformat()
    members = [
        item for item in read_repository.list_members(user.organization_id)
        if item.workforce_member_id == member_id
    ]
    if not members:
        raise HTTPException(status_code=404, detail="Driver Workforce non trovato.")
    snapshot = consecutivity_snapshots(user.organization_id, target, members)[member_id]
    return {
        "snapshot": snapshot,
        "override_history": override_service.history(user.organization_id, member_id),
    }


@router.patch("/members/{member_id}", response_model=WorkforceMember)
def update_member(
    member_id: int,
    request: WorkforceMemberUpdateRequest,
    http_request: Request,
):
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.update_member(
            member_id,
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            request.actor,
            user.organization_id,
        )
    except (DemoWorkspaceResetRequiredError, WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.get("/calendar", response_model=WorkforceCalendarResponse)
def calendar(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    member_id: int | None = Query(default=None, gt=0),
) -> WorkforceCalendarResponse:
    return WorkforceCalendarResponse(
        items=workforce_service.list_calendar(date_from, date_to, member_id)
    )


@router.get("/coverage", response_model=WorkforceCoverageResponse)
def coverage(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> WorkforceCoverageResponse:
    return WorkforceCoverageResponse(
        items=workforce_service.coverage(date_from, date_to)
    )


@router.get("/changes", response_model=WorkforceChangesResponse)
def changes(limit: int = Query(default=100, ge=1, le=1000)) -> WorkforceChangesResponse:
    return WorkforceChangesResponse(items=workforce_service.list_changes(limit))


@router.post("/import/preview", response_model=WorkforceImportPreview)
async def import_preview(file: UploadFile = File(...)) -> WorkforceImportPreview:
    try:
        content, filename = await _read_upload(file)
        return workforce_service.preview_import(content, filename)
    except (WorkbookProfileError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/import", response_model=WorkforceImportResult)
async def import_confirmed(
    file: UploadFile = File(...),
    confirmed_fingerprint: str = Form(...),
    actor: str = Form("local_operator"),
) -> WorkforceImportResult:
    try:
        ensure_real_data_write_allowed()
        content, filename = await _read_upload(file)
        return workforce_service.apply_import(
            content, filename, confirmed_fingerprint, actor
        )
    except (DemoWorkspaceResetRequiredError, WorkforceImportError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/day-status", response_model=WorkforceDayStatus)
def create_day_status(
    request: WorkforceDayStatusRequest,
    http_request: Request,
) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}), request.actor,
            organization_id=user.organization_id,
        )
    except (DemoWorkspaceResetRequiredError, WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.patch("/day-status/{status_id}", response_model=WorkforceDayStatus)
def update_day_status(
    status_id: int,
    request: WorkforceDayStatusRequest,
    http_request: Request,
) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}), request.actor, status_id,
            user.organization_id,
        )
    except (
        DemoWorkspaceResetRequiredError,
        WorkforceMemberNotFoundError,
        WorkforceStatusNotFoundError,
        WorkforceValidationError,
    ) as exc:
        raise _write_error(exc) from exc


@router.get("/contracts/core")
def contracts_core(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict[str, object]:
    return workforce_service.core_contracts(date_from, date_to)


@router.get("/export")
def export(section: str = Query(default="calendar", pattern="^(calendar|coverage|changes)$")) -> Response:
    content = workforce_service.export_csv(section)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="workforce-{section}.csv"'
        },
    )

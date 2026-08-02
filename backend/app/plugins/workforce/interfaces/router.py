from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile

from app.importers.excel_reader import validate_upload
from app.importers.workbook_profiler.errors import WorkbookProfileError
from app.plugins.workforce.application import workforce_service
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


@router.get("/status", response_model=WorkforceStatusResponse)
def status() -> WorkforceStatusResponse:
    members = workforce_service.list_members()
    return WorkforceStatusResponse(
        member_count=len(members),
        latest_import=read_repository.latest_import_summary(),
    )


@router.get("/members", response_model=WorkforceMembersResponse)
def members() -> WorkforceMembersResponse:
    return WorkforceMembersResponse(items=workforce_service.list_members())


@router.get("/foundation", response_model=WorkforceFoundationSnapshot)
def foundation(
    operation_date: str | None = Query(default=None),
) -> WorkforceFoundationSnapshot:
    try:
        return foundation_snapshot(operation_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data operativa non valida.") from exc


@router.patch("/members/{member_id}", response_model=WorkforceMember)
def update_member(member_id: int, request: WorkforceMemberUpdateRequest):
    try:
        ensure_real_data_write_allowed()
        return workforce_service.update_member(
            member_id,
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            request.actor,
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
def create_day_status(request: WorkforceDayStatusRequest) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}), request.actor
        )
    except (DemoWorkspaceResetRequiredError, WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.patch("/day-status/{status_id}", response_model=WorkforceDayStatus)
def update_day_status(status_id: int, request: WorkforceDayStatusRequest) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}), request.actor, status_id
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

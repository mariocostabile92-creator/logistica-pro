import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.domain.core_language.models import ResourceAvailability
from app.importers.excel_reader import read_validated_upload
from app.importers.workbook_profiler.errors import (
    WorkbookImportBlockedError,
    WorkbookProfileError,
)
from app.plugins.fleet.application import sync_service
from app.plugins.fleet.domain.errors import FleetSyncError
from app.plugins.fleet.domain.sync_models import FleetSyncPreview, FleetSyncResult
from app.workspace.status_service import (
    DemoWorkspaceResetRequiredError,
    ensure_real_data_write_allowed,
)


router = APIRouter(
    prefix="/api/plugins/fleet/v1",
    tags=["fleet-plugin-v1"],
)


def _mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        values = json.loads(raw)
        return {
            str(item["source_column"]): (
                str(item["target_field"]) if item.get("target_field") else None
            )
            for item in values
        }
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FLEET_SYNC_MAPPING_INVALID",
                "message": "Il mapping Fleet non e valido.",
            },
        ) from exc


def _selected_rows(raw: str) -> list[int]:
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in values
        ):
            raise ValueError
        return values
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FLEET_SYNC_SELECTION_INVALID",
                "message": "La selezione Fleet non e valida.",
            },
        ) from exc


async def _content(file: UploadFile) -> tuple[bytes, str]:
    content = await read_validated_upload(file)
    return content, file.filename or "fleet-registry-upload"


def _profile_error(exc: WorkbookProfileError) -> HTTPException:
    detail: dict[str, object] = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, WorkbookImportBlockedError):
        detail["blocking_reasons"] = [
            item.model_dump(mode="json") for item in exc.issues
        ]
    return HTTPException(status_code=422, detail=detail)


@router.post("/sync/preview", response_model=FleetSyncPreview)
async def preview(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    column_mapping: str | None = Form(None),
) -> FleetSyncPreview:
    try:
        content, filename = await _content(file)
        return sync_service.preview_sync(
            content=content,
            filename=filename,
            sheet_name=sheet_name,
            header_row=header_row,
            manual_mapping=_mapping(column_mapping),
        )
    except WorkbookProfileError as exc:
        raise _profile_error(exc) from exc


@router.post("/sync/confirm", response_model=FleetSyncResult)
async def confirm(
    file: UploadFile = File(...),
    confirmed_fingerprint: str = Form(...),
    selected_rows: str = Form(...),
    actor: str = Form("local_operator"),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    column_mapping: str | None = Form(None),
) -> FleetSyncResult:
    try:
        ensure_real_data_write_allowed()
        content, filename = await _content(file)
        return sync_service.confirm_sync(
            content=content,
            filename=filename,
            confirmed_fingerprint=confirmed_fingerprint,
            selected_rows=_selected_rows(selected_rows),
            actor=actor,
            sheet_name=sheet_name,
            header_row=header_row,
            manual_mapping=_mapping(column_mapping),
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_WORKSPACE_RESET_REQUIRED",
                "message": str(exc),
            },
        ) from exc
    except WorkbookProfileError as exc:
        raise _profile_error(exc) from exc
    except FleetSyncError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/sync/latest")
def latest() -> dict[str, object]:
    value = sync_service.latest_sync()
    if not value:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "FLEET_SYNC_NOT_FOUND",
                "message": "Nessuna sincronizzazione Fleet disponibile.",
            },
        )
    return value


@router.get("/availability", response_model=list[ResourceAvailability])
def availability() -> list[ResourceAvailability]:
    return sync_service.core_availability()

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.adapters.registry import get_active_tabular_import_adapter
from app.importers.workbook_profiler.errors import (
    WorkbookImportBlockedError,
    WorkbookProfileError,
    WorkbookReadError,
    WorkbookSelectionError,
)
from app.schemas.import_schema import ImportPreviewResponse, ImportResultResponse
from app.services.import_service import import_file, preview_file
from app.workspace.status_service import DemoWorkspaceResetRequiredError


router = APIRouter(prefix="/api/imports", tags=["imports"])


def _manual_mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkbookSelectionError(
            "Il mapping manuale non usa un formato JSON valido."
        ) from exc
    if not isinstance(payload, list):
        raise WorkbookSelectionError(
            "Il mapping manuale deve essere una lista di colonne."
        )
    mapping: dict[str, str | None] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise WorkbookSelectionError(
                "Ogni mapping deve indicare colonna e campo."
            )
        source = item.get("source_column")
        target = item.get("target_field")
        if not isinstance(source, str) or (
            target is not None and not isinstance(target, str)
        ):
            raise WorkbookSelectionError(
                "Il mapping contiene valori non validi."
            )
        mapping[source] = target or None
    return mapping


def _workbook_http_error(exc: WorkbookProfileError) -> HTTPException:
    if isinstance(exc, WorkbookReadError):
        status_code = 400
    else:
        status_code = 422
    detail = {
        "code": exc.code,
        "message": str(exc),
    }
    if isinstance(exc, WorkbookImportBlockedError):
        detail["blocking_reasons"] = [
            item.model_dump(mode="json") for item in exc.issues
        ]
    return HTTPException(status_code=status_code, detail=detail)


async def _import_operational_file(
    *,
    file: UploadFile,
    dataset_type: str,
    sheet_name: str | None,
    header_row: int | None,
    column_mapping: str | None,
) -> ImportResultResponse:
    try:
        return await import_file(
            file=file,
            dataset_type=dataset_type,
            adapter=get_active_tabular_import_adapter(),
            sheet_name=sheet_name,
            header_row=header_row,
            manual_mapping=_manual_mapping(column_mapping),
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
        raise _workbook_http_error(exc) from exc


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    dataset_type: str = Form("planning"),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    column_mapping: str | None = Form(None),
) -> ImportPreviewResponse:
    try:
        return await preview_file(
            file=file,
            dataset_type=dataset_type,
            adapter=get_active_tabular_import_adapter(),
            sheet_name=sheet_name,
            header_row=header_row,
            manual_mapping=_manual_mapping(column_mapping),
        )
    except WorkbookProfileError as exc:
        raise _workbook_http_error(exc) from exc


@router.post("/planning", response_model=ImportResultResponse)
async def import_planning(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    column_mapping: str | None = Form(None),
) -> ImportResultResponse:
    return await _import_operational_file(
        file=file,
        dataset_type="planning",
        sheet_name=sheet_name,
        header_row=header_row,
        column_mapping=column_mapping,
    )


@router.post("/fleet", response_model=ImportResultResponse)
async def import_fleet(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    column_mapping: str | None = Form(None),
) -> ImportResultResponse:
    return await _import_operational_file(
        file=file,
        dataset_type="fleet",
        sheet_name=sheet_name,
        header_row=header_row,
        column_mapping=column_mapping,
    )

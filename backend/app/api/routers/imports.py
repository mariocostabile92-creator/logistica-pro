from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.adapters.registry import get_active_tabular_import_adapter
from app.schemas.import_schema import ImportPreviewResponse, ImportResultResponse
from app.services.import_service import import_file, preview_file
from app.workspace.status_service import DemoWorkspaceResetRequiredError


router = APIRouter(prefix="/api/imports", tags=["imports"])


async def _import_operational_file(
    *,
    file: UploadFile,
    dataset_type: str,
    sheet_name: str | None,
) -> ImportResultResponse:
    try:
        return await import_file(
            file=file,
            dataset_type=dataset_type,
            adapter=get_active_tabular_import_adapter(),
            sheet_name=sheet_name,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_WORKSPACE_RESET_REQUIRED",
                "message": str(exc),
            },
        ) from exc


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    dataset_type: str = Form("planning"),
    sheet_name: str | None = Form(None),
) -> ImportPreviewResponse:
    return await preview_file(
        file=file,
        dataset_type=dataset_type,
        adapter=get_active_tabular_import_adapter(),
        sheet_name=sheet_name,
    )


@router.post("/planning", response_model=ImportResultResponse)
async def import_planning(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
) -> ImportResultResponse:
    return await _import_operational_file(
        file=file,
        dataset_type="planning",
        sheet_name=sheet_name,
    )


@router.post("/fleet", response_model=ImportResultResponse)
async def import_fleet(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
) -> ImportResultResponse:
    return await _import_operational_file(
        file=file,
        dataset_type="fleet",
        sheet_name=sheet_name,
    )

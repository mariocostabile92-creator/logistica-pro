from fastapi import UploadFile

from app.importers.adapter_contract import TabularImportAdapter
from app.importers.excel_reader import read_tabular, validate_upload
from app.importers.fleet_importer import normalize_fleet_rows
from app.importers.planning_importer import normalize_planning_rows
from app.repositories.import_repository import save_import
from app.schemas.import_schema import (
    ColumnMappingSuggestion,
    ImportPreviewResponse,
    ImportResultResponse,
)
from app.services.normalization_service import suggest_mapping
from app.workspace.status_service import ensure_real_data_write_allowed


def _mapping_for(
    columns: list[str],
    dataset_type: str,
    adapter: TabularImportAdapter,
) -> list[ColumnMappingSuggestion]:
    return suggest_mapping(
        columns,
        adapter.aliases_for(dataset_type),
    )


async def preview_file(
    file: UploadFile,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
) -> ImportPreviewResponse:
    content = await file.read()
    validate_upload(file, content)
    table = read_tabular(
        content,
        file.filename or "upload",
        sheet_name=sheet_name,
        preview_only=True,
    )
    mapping = _mapping_for(
        table["columns"],
        dataset_type,
        adapter,
    )
    return ImportPreviewResponse(
        dataset_type=dataset_type,
        original_filename=file.filename or "upload",
        sheets=table["sheets"],
        selected_sheet=table["selected_sheet"],
        columns=table["columns"],
        recognized_columns=[
            item
            for item in mapping
            if item.target_field and not item.requires_confirmation
        ],
        unrecognized_columns=[
            item.source_column
            for item in mapping
            if item.requires_confirmation or not item.target_field
        ],
        preview_rows=table["rows"],
    )


async def import_file(
    file: UploadFile,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
) -> ImportResultResponse:
    ensure_real_data_write_allowed()
    content = await file.read()
    validate_upload(file, content)
    return import_tabular_content(
        content=content,
        original_filename=file.filename or "upload",
        dataset_type=dataset_type,
        adapter=adapter,
        sheet_name=sheet_name,
    )


def import_tabular_content(
    *,
    content: bytes,
    original_filename: str,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
) -> ImportResultResponse:
    if dataset_type not in {"planning", "fleet"}:
        raise ValueError("Tipo dataset non supportato.")
    table = read_tabular(
        content,
        original_filename,
        sheet_name=sheet_name,
        preview_only=False,
    )
    mapping = _mapping_for(
        table["columns"],
        dataset_type,
        adapter,
    )
    if dataset_type == "fleet":
        normalized = normalize_fleet_rows(table["rows"], mapping)
    else:
        normalized = normalize_planning_rows(table["rows"], mapping)
    normalized_dicts = [row.model_dump() for row in normalized]
    import_id = save_import(
        dataset_type=dataset_type,
        original_filename=original_filename,
        sheet_name=table["selected_sheet"],
        column_mapping=[item.model_dump() for item in mapping],
        normalized_rows=normalized_dicts,
    )
    return ImportResultResponse(
        import_id=import_id,
        dataset_type=dataset_type,
        rows_imported=len(normalized_dicts),
        mapping=mapping,
        normalized_rows=normalized_dicts,
    )

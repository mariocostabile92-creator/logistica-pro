from fastapi import UploadFile

from app.importers.adapter_contract import TabularImportAdapter
from app.importers.excel_reader import read_validated_upload
from app.importers.fleet_importer import normalize_fleet_rows
from app.importers.planning_importer import normalize_planning_rows
from app.importers.workbook_profiler.errors import (
    WorkbookImportBlockedError,
)
from app.importers.workbook_profiler.preview_builder import (
    build_workbook_profile,
)
from app.repositories.import_repository import save_import
from app.schemas.import_schema import (
    ImportPreviewResponse,
    ImportResultResponse,
)
from app.workspace.status_service import ensure_real_data_write_allowed


async def preview_file(
    file: UploadFile,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
) -> ImportPreviewResponse:
    content = await read_validated_upload(file)
    profile = build_workbook_profile(
        content=content,
        filename=file.filename or "upload",
        dataset_type=dataset_type,
        aliases=adapter.aliases_for(dataset_type),
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )
    alternative_sheets = [
        item
        for item in profile.sheet_profiles
        if item.name != profile.selected_sheet.name and not item.ignored
    ]
    ignored_sheets = [
        item for item in profile.sheet_profiles if item.ignored
    ]
    alternative_headers = (
        profile.selected_sheet_profile.header_candidates[1:]
        if profile.selected_header
        else profile.selected_sheet_profile.header_candidates
    )
    destinations = {
        "DAILY_OPERATIONAL_PLANNING": (
            "daily_operations",
            "Importa nel Planning operativo",
        ),
        "WORKFORCE_SCHEDULE": (
            "workforce",
            "Importa in Workforce Planning",
        ),
        "FLEET_REGISTRY": (
            "fleet_registry",
            "Sincronizza con Asset Registry",
        ),
        "UNKNOWN_WORKBOOK": ("manual_review", "Verifica manuale"),
    }
    target, action_label = destinations[
        profile.classification.workbook_type.value
    ]
    return ImportPreviewResponse(
        dataset_type=dataset_type,
        original_filename=file.filename or "upload",
        sheets=[item.name for item in profile.sheet_profiles],
        selected_sheet=profile.selected_sheet.name,
        columns=profile.columns,
        recognized_columns=profile.recognized_columns,
        unrecognized_columns=[
            *profile.ignored_columns,
            *profile.unknown_columns,
        ],
        preview_rows=profile.sample_rows,
        workbook_type=profile.classification.workbook_type,
        workbook_type_confidence=profile.classification.confidence,
        workbook_type_reason=profile.classification.reason,
        selected_sheet_score=profile.selected_sheet_profile.score,
        selected_sheet_reason=profile.selected_sheet_profile.reason,
        available_sheets=profile.sheet_profiles,
        alternative_sheets=alternative_sheets,
        ignored_sheets=ignored_sheets,
        selected_header_row=(
            profile.selected_header.row_index
            if profile.selected_header
            else None
        ),
        selected_header_confidence=(
            profile.selected_header.confidence
            if profile.selected_header
            else 0
        ),
        selected_header_reason=(
            profile.selected_header.reason
            if profile.selected_header
            else ""
        ),
        alternative_header_rows=alternative_headers,
        total_rows=len(profile.table_rows),
        detected_columns=profile.columns,
        column_mappings=profile.mapping,
        mapping_options=profile.mapping_options,
        ignored_columns=profile.ignored_columns,
        unknown_columns=profile.unknown_columns,
        mapping_confidence=profile.mapping_confidence,
        import_allowed=profile.import_allowed,
        blocking_reasons=profile.blocking_reasons,
        warnings=profile.warnings,
        sample_rows=profile.sample_rows,
        recommended_target=target,
        recommended_action_label=action_label,
    )


async def import_file(
    file: UploadFile,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
) -> ImportResultResponse:
    ensure_real_data_write_allowed()
    content = await read_validated_upload(file)
    return import_tabular_content(
        content=content,
        original_filename=file.filename or "upload",
        dataset_type=dataset_type,
        adapter=adapter,
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )


def import_tabular_content(
    *,
    content: bytes,
    original_filename: str,
    dataset_type: str,
    adapter: TabularImportAdapter,
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
) -> ImportResultResponse:
    if dataset_type not in {"planning", "fleet"}:
        raise ValueError("Tipo dataset non supportato.")
    profile = build_workbook_profile(
        content=content,
        filename=original_filename,
        dataset_type=dataset_type,
        aliases=adapter.aliases_for(dataset_type),
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )
    if not profile.import_allowed:
        raise WorkbookImportBlockedError(profile.blocking_reasons)
    if dataset_type == "fleet":
        normalized = normalize_fleet_rows(
            profile.table_rows,
            profile.mapping,
            row_numbers=profile.row_numbers,
        )
    else:
        normalized = normalize_planning_rows(
            profile.table_rows,
            profile.mapping,
            row_numbers=profile.row_numbers,
        )
    normalized_dicts = [
        row.model_dump(mode="json") for row in normalized
    ]
    import_id = save_import(
        dataset_type=dataset_type,
        original_filename=original_filename,
        sheet_name=profile.selected_sheet.name,
        column_mapping=[
            item.model_dump(mode="json") for item in profile.mapping
        ],
        normalized_rows=normalized_dicts,
    )
    return ImportResultResponse(
        import_id=import_id,
        dataset_type=dataset_type,
        rows_imported=len(normalized_dicts),
        mapping=profile.mapping,
        normalized_rows=normalized_dicts,
        workbook_type=profile.classification.workbook_type,
        selected_header_row=(
            profile.selected_header.row_index
            if profile.selected_header
            else None
        ),
    )

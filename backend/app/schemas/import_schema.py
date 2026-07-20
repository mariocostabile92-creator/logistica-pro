from typing import Literal

from pydantic import BaseModel, Field

from app.importers.workbook_profiler.models import (
    HeaderCandidate,
    MappingFieldOption,
    ProfileIssue,
    SheetProfile,
    WorkbookType,
)


class ColumnMappingSuggestion(BaseModel):
    source_column: str
    target_field: str | None
    confidence: float
    requires_confirmation: bool
    status: Literal[
        "recognized",
        "review",
        "ignored",
        "unknown",
    ] = "unknown"


class ImportPreviewResponse(BaseModel):
    dataset_type: str
    original_filename: str
    sheets: list[str] = Field(default_factory=list)
    selected_sheet: str | None = None
    columns: list[str]
    recognized_columns: list[ColumnMappingSuggestion]
    unrecognized_columns: list[str]
    preview_rows: list[dict[str, object]]
    workbook_type: WorkbookType = WorkbookType.UNKNOWN_WORKBOOK
    workbook_type_confidence: float = 0
    workbook_type_reason: str = ""
    selected_sheet_score: float = 0
    selected_sheet_reason: str = ""
    available_sheets: list[SheetProfile] = Field(default_factory=list)
    alternative_sheets: list[SheetProfile] = Field(default_factory=list)
    ignored_sheets: list[SheetProfile] = Field(default_factory=list)
    selected_header_row: int | None = None
    selected_header_confidence: float = 0
    selected_header_reason: str = ""
    alternative_header_rows: list[HeaderCandidate] = Field(
        default_factory=list
    )
    total_rows: int = 0
    detected_columns: list[str] = Field(default_factory=list)
    column_mappings: list[ColumnMappingSuggestion] = Field(
        default_factory=list
    )
    mapping_options: list[MappingFieldOption] = Field(default_factory=list)
    ignored_columns: list[str] = Field(default_factory=list)
    unknown_columns: list[str] = Field(default_factory=list)
    mapping_confidence: float = 0
    import_allowed: bool = False
    blocking_reasons: list[ProfileIssue] = Field(default_factory=list)
    warnings: list[ProfileIssue] = Field(default_factory=list)
    sample_rows: list[dict[str, object]] = Field(default_factory=list)


class ImportResultResponse(BaseModel):
    import_id: int
    dataset_type: str
    rows_imported: int
    mapping: list[ColumnMappingSuggestion]
    normalized_rows: list[dict[str, object]]
    workbook_type: WorkbookType | None = None
    selected_header_row: int | None = None

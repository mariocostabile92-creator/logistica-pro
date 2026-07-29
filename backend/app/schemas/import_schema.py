from pydantic import BaseModel, Field


class ColumnMappingSuggestion(BaseModel):
    source_column: str
    target_field: str | None
    confidence: float
    requires_confirmation: bool


class ImportPreviewResponse(BaseModel):
    dataset_type: str
    original_filename: str
    sheets: list[str] = Field(default_factory=list)
    selected_sheet: str | None = None
    columns: list[str]
    recognized_columns: list[ColumnMappingSuggestion]
    unrecognized_columns: list[str]
    preview_rows: list[dict[str, object]]


class ImportResultResponse(BaseModel):
    import_id: int
    dataset_type: str
    rows_imported: int
    mapping: list[ColumnMappingSuggestion]
    normalized_rows: list[dict[str, object]]

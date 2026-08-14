from enum import Enum

from pydantic import BaseModel, Field


class ForecastReconciliationStatus(str, Enum):
    READY = "READY"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    NO_ELIGIBLE_IMPORT = "NO_ELIGIBLE_IMPORT"
    SOURCE_NOT_RECOVERABLE = "SOURCE_NOT_RECOVERABLE"


class ForecastReconciliationPreview(BaseModel):
    status: ForecastReconciliationStatus
    workforce_import_id: int | None = None
    original_filename: str | None = None
    import_fingerprint: str | None = None
    source_filename: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    next_day_affected: int = Field(default=0, ge=0)
    same_day_a_suspect: int = Field(default=0, ge=0)
    same_day_b_c_suspect: int = Field(default=0, ge=0)
    persisted_rows_matched: int = Field(default=0, ge=0)
    manual_overrides_preserved: int = Field(default=0, ge=0)
    effective_rows_before: int = Field(default=0, ge=0)
    effective_rows_after: int = Field(default=0, ge=0)
    preview_fingerprint: str | None = None
    action_required: str

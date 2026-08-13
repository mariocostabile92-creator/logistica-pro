from enum import Enum

from pydantic import BaseModel, Field


class LegacyCoverageBackfillStatus(str, Enum):
    READY = "READY"
    ALREADY_COMPLETE = "ALREADY_COMPLETE"
    SOURCE_NOT_RECOVERABLE = "SOURCE_NOT_RECOVERABLE"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    NO_ELIGIBLE_IMPORT = "NO_ELIGIBLE_IMPORT"


class LegacyCoverageBackfillPreview(BaseModel):
    status: LegacyCoverageBackfillStatus
    workforce_import_id: int | None = None
    original_filename: str | None = None
    import_fingerprint: str | None = None
    imported_at: str | None = None
    source_recoverable: bool = False
    source_filename: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    next_day_count: int = Field(default=0, ge=0)
    same_day_a_count: int = Field(default=0, ge=0)
    same_day_b_c_count: int = Field(default=0, ge=0)
    requirements_expected: int = Field(default=0, ge=0)
    existing_rows: int = Field(default=0, ge=0)
    existing_modern_rows: int = Field(default=0, ge=0)
    requirements_missing: int = Field(default=0, ge=0)
    preview_fingerprint: str | None = None
    action_required: str


class LegacyCoverageBackfillResult(LegacyCoverageBackfillPreview):
    requirements_created: int = Field(default=0, ge=0)
    requirements_skipped: int = Field(default=0, ge=0)
    idempotent: bool = False


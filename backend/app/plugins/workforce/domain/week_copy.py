from pydantic import BaseModel, Field

from app.plugins.workforce.domain.models import WorkforceDayStatus


class WorkforceWeekCopyConflictError(Exception):
    code = "WORKFORCE_WEEK_COPY_STALE"


class WorkforceWeekCopyValue(BaseModel):
    status_code: str
    availability: bool
    shift_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None


class WorkforceWeekCopyDay(BaseModel):
    source_date: str
    target_date: str
    source: WorkforceWeekCopyValue | None = None
    target: WorkforceWeekCopyValue | None = None
    will_overwrite: bool = False


class WorkforceWeekCopyPreview(BaseModel):
    workforce_member_id: int
    source_week_start: str
    source_week_end: str
    target_week_start: str
    target_week_end: str
    days: list[WorkforceWeekCopyDay] = Field(min_length=7, max_length=7)
    overwrite_count: int = Field(ge=0, le=7)
    missing_count: int = Field(ge=0, le=7)
    fingerprint: str = Field(min_length=64, max_length=64)


class WorkforceWeekCopyResult(BaseModel):
    items: list[WorkforceDayStatus]
    copied_count: int = Field(ge=0, le=7)
    overwritten_count: int = Field(ge=0, le=7)
    skipped_missing_count: int = Field(ge=0, le=7)
    target_week_start: str
    target_week_end: str

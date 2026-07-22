from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit


class _TimelineModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningTimelineCategory(str, Enum):
    IMPORT = "IMPORT"
    VALIDATION = "VALIDATION"
    WORKFORCE = "WORKFORCE"
    FLEET = "FLEET"
    READINESS = "READINESS"
    CONFLICT = "CONFLICT"
    RUNTIME = "RUNTIME"
    SYSTEM = "SYSTEM"
    LEGACY = "LEGACY"


class PlanningTimelineSeverity(str, Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PlanningTimelineMetadata(_TimelineModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class PlanningTimelineEvent(_TimelineModel):
    id: str = Field(min_length=1)
    timestamp: datetime
    category: PlanningTimelineCategory
    severity: PlanningTimelineSeverity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source: str = Field(min_length=1)
    operational_unit: OperationalUnit
    planning_date: date
    reference: str | None = None
    related_conflicts: tuple[str, ...] = Field(default_factory=tuple)
    related_readiness: str | None = None
    metadata: tuple[PlanningTimelineMetadata, ...] = Field(
        default_factory=tuple
    )

    _validate_timestamp = field_validator("timestamp")(_require_timezone)


class PlanningTimelineGroup(_TimelineModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    event_count: int = Field(ge=1, le=100)
    event_ids: tuple[str, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_count(self):
        if self.event_count != len(self.event_ids):
            raise ValueError("Group count must match event identifiers.")
        return self


class PlanningTimelineReport(_TimelineModel):
    event_count: int = Field(ge=0, le=100)
    last_updated: datetime | None = None
    current_status: str = Field(min_length=1)
    groups: tuple[PlanningTimelineGroup, ...] = Field(default_factory=tuple)
    events: tuple[PlanningTimelineEvent, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )

    @field_validator("last_updated")
    @classmethod
    def validate_last_updated(cls, value):
        return _require_timezone(value) if value is not None else value

    @model_validator(mode="after")
    def validate_report(self):
        if self.event_count != len(self.events):
            raise ValueError("Report count must match events.")
        timestamps = tuple(item.timestamp for item in self.events)
        if timestamps != tuple(sorted(timestamps, reverse=True)):
            raise ValueError("Timeline events must be newest first.")
        expected_update = self.events[0].timestamp if self.events else None
        if self.last_updated != expected_update:
            raise ValueError("last_updated must match the newest event.")
        event_ids = tuple(item.id for item in self.events)
        grouped_ids = tuple(
            event_id
            for group in self.groups
            for event_id in group.event_ids
        )
        if len(grouped_ids) != len(set(grouped_ids)):
            raise ValueError("An event cannot belong to multiple groups.")
        if set(grouped_ids) != set(event_ids):
            raise ValueError("Every event must belong to one group.")
        return self


class PlanningTimelineResult(_TimelineModel):
    report: PlanningTimelineReport

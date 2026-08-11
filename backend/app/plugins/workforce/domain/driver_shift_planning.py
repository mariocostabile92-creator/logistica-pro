from enum import StrEnum

from pydantic import BaseModel, Field


class DriverShiftPlanningStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class DriverShiftPlanningSourceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_FOR_MERGE = "UNAVAILABLE_FOR_MERGE"


class MergeClassification(StrEnum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    POTENTIAL_CONFLICT = "POTENTIAL_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    DISTINCT_ASSIGNMENT = "DISTINCT_ASSIGNMENT"
    UNRESOLVED_IDENTITY = "UNRESOLVED_IDENTITY"


class DriverShiftPlanningError(ValueError):
    code = "DRIVER_SHIFT_PLANNING_INVALID"


class DriverShiftPlanningNotFoundError(DriverShiftPlanningError):
    code = "DRIVER_SHIFT_PLANNING_NOT_FOUND"


class DriverShiftPlanningSourceNotFoundError(DriverShiftPlanningError):
    code = "DRIVER_SHIFT_PLANNING_SOURCE_NOT_FOUND"


class DriverShiftPlanning(BaseModel):
    id: int
    organization_id: str
    label: str | None = None
    period_start: str
    period_end: str
    status: DriverShiftPlanningStatus
    version: int = Field(ge=1)
    created_at: str
    created_by: str
    updated_at: str


class DriverShiftPlanningSource(BaseModel):
    id: int
    organization_id: str
    driver_shift_planning_id: int
    workforce_import_id: int
    source_filename: str
    imported_at: str
    row_count: int = Field(ge=0)
    source_order: int = Field(ge=0)
    added_at: str
    added_by: str
    status: DriverShiftPlanningSourceStatus
    date_from: str | None = None
    date_to: str | None = None
    period_compatibility: str
    warnings: list[str] = Field(default_factory=list)


class MergeSourceReference(BaseModel):
    workforce_import_id: int
    filename: str
    sheet: str
    row_number: int = Field(gt=0)
    source_record_key: str
    source_order: int = Field(ge=0)


class MergeAlternative(BaseModel):
    source_external_identifier: str | None = None
    driver_display_name: str | None = None
    transporter_id: str | None = None
    status_code: str | None = None
    availability: bool | None = None
    shift_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    station: str | None = None
    notes: str | None = None
    source_references: list[MergeSourceReference] = Field(default_factory=list)


class DriverShiftPlanningMergeRow(BaseModel):
    identity_key: str | None = None
    workforce_member_id: int | None = None
    source_external_identifier: str | None = None
    display_name: str | None = None
    operational_date: str
    status_code: str | None = None
    availability: bool | None = None
    shift_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    station: str | None = None
    transporter_id: str | None = None
    classification: MergeClassification
    source_references: list[MergeSourceReference] = Field(default_factory=list)
    conflicting_alternatives: list[MergeAlternative] = Field(default_factory=list)


class DriverShiftPlanningMergeSummary(BaseModel):
    total_source_rows: int = 0
    unified_rows: int = 0
    distinct_rows: int = 0
    exact_duplicates: int = 0
    potential_conflicts: int = 0
    identity_conflicts: int = 0
    unresolved_rows: int = 0


class DriverShiftPlanningMergePreview(BaseModel):
    planning: DriverShiftPlanning
    sources: list[DriverShiftPlanningSource] = Field(default_factory=list)
    summary: DriverShiftPlanningMergeSummary
    rows: list[DriverShiftPlanningMergeRow] = Field(default_factory=list)
    filtered_rows: int = 0
    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(default=None, ge=1)
    has_more: bool = False


class DriverShiftPlanningList(BaseModel):
    items: list[DriverShiftPlanning] = Field(default_factory=list)
    current: DriverShiftPlanning | None = None

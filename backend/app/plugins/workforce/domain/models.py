from enum import Enum

from pydantic import BaseModel, Field

from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot


class WorkforceValueOrigin(str, Enum):
    IMPORTED = "imported"
    MANUAL = "manual"


class OperationalCycle(str, Enum):
    NEXT_DAY = "NEXT_DAY"
    SAME_DAY = "SAME_DAY"
    NOT_SET = "NOT_SET"


class WorkforceMember(BaseModel):
    workforce_member_id: int
    external_identifier: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    station: str | None = None
    employment_type: str | None = None
    operational_cycle: OperationalCycle = OperationalCycle.NOT_SET
    contract_start: str | None = None
    contract_end: str | None = None
    weekly_hours: float | None = Field(default=None, ge=0)
    capabilities: list[str] = Field(default_factory=list)
    operational_notes: str | None = None
    phone: str | None = None
    email: str | None = None
    is_reserve: bool = False
    active: bool = True
    source_reference: str
    created_at: str
    updated_at: str
    organization_id: str = "default"


class WorkforceDayStatus(BaseModel):
    status_id: int
    workforce_member_id: int
    date: str
    status_code: str
    availability: bool
    shift_code: str | None = None
    operational_activity: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    source_reference: str
    observed_or_confirmed: WorkforceValueOrigin
    updated_at: str
    organization_id: str = "default"


class WorkforceRequirement(BaseModel):
    requirement_id: int
    date: str
    operational_unit_id: str
    required_resources: int = Field(ge=0)
    required_capabilities: list[str] = Field(default_factory=list)
    source: str
    version: int = Field(ge=1)


class WorkforceCoverage(BaseModel):
    date: str
    operational_unit_id: str | None = None
    required: int | None = Field(default=None, ge=0)
    available: int = Field(ge=0)
    scheduled: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    margin: int | None = None
    status: str
    limitations: list[str] = Field(default_factory=list)


class WorkforceChange(BaseModel):
    change_id: int
    entity_type: str
    entity_id: str
    actor: str
    timestamp: str
    before: dict[str, object] | None = None
    after: dict[str, object]
    reason: str
    source: str


class WorkforceImportSheet(BaseModel):
    name: str
    responsibility: str
    header_row: int | None = None
    confidence: float = Field(ge=0, le=1)
    importable_rows: int = Field(default=0, ge=0)


class WorkforceMapping(BaseModel):
    sheet_name: str
    source_column: str
    target_field: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: str


class WorkforceImportPreview(BaseModel):
    workbook_type: str = "WORKFORCE_SCHEDULE"
    fingerprint: str
    sheets: list[WorkforceImportSheet]
    mappings: list[WorkforceMapping]
    people_detected: int = Field(ge=0)
    date_from: str | None = None
    date_to: str | None = None
    shift_codes: list[str] = Field(default_factory=list)
    contracts_detected: int = Field(default=0, ge=0)
    next_day_detected: int = Field(default=0, ge=0)
    same_day_detected: int = Field(default=0, ge=0)
    operational_cycle_unrecognized: int = Field(default=0, ge=0)
    absences_detected: int = Field(default=0, ge=0)
    excluded_rows: int = Field(default=0, ge=0)
    phone_detected: int = Field(default=0, ge=0)
    email_detected: int = Field(default=0, ge=0)
    invalid_contacts: int = Field(default=0, ge=0)
    contact_conflicts: int = Field(default=0, ge=0)
    confirmation_columns: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    matrix: list[dict[str, object]] = Field(default_factory=list)


class WorkforceImportResult(BaseModel):
    fingerprint: str
    idempotent: bool
    members_created: int = 0
    members_updated: int = 0
    statuses_created: int = 0
    statuses_updated: int = 0
    requirements_created: int = 0
    sheets_imported: list[str] = Field(default_factory=list)


class WorkforceBriefingSnapshot(BaseModel):
    date: str
    coverage: WorkforceCoverage
    absences: int = 0
    contracts_expiring: int = 0
    missing_capabilities: list[str] = Field(default_factory=list)


class WorkforceDriverReadiness(BaseModel):
    workforce_member_id: int
    external_identifier: str
    first_name: str
    last_name: str
    display_name: str
    role: str | None = None
    station: str | None = None
    contract: str | None = None
    operational_cycle: OperationalCycle = OperationalCycle.NOT_SET
    availability_status: str
    availability_label: str
    callability_status: str
    callability_label: str
    callability_reason: str = Field(min_length=1)
    callability_tone: str
    callable: bool
    is_reserve: bool = False
    rest: bool = False
    holiday: bool = False
    sickness: bool = False
    leave: bool = False
    consecutive_days: int | None = None
    consecutivity_status: str = "not_evaluated"
    consecutivity: ConsecutivitySnapshot | None = None
    capabilities: list[str] = Field(default_factory=list)
    operational_notes: str | None = None
    convocation_status: str = "not_started"
    limitations: list[str] = Field(default_factory=list)
    status_history: list[dict[str, str | bool | None]] = Field(default_factory=list)
    last_updated_at: str


class WorkforceFoundationSummary(BaseModel):
    total: int = 0
    available: int = 0
    callable: int = 0
    limited: int = 0
    holiday: int = 0
    sickness: int = 0
    leave: int = 0
    rest: int = 0
    not_callable: int = 0
    reserves: int = 0
    at_limit: int = 0
    rest_recommended: int = 0
    insufficient_data: int = 0
    active_overrides: int = 0


class WorkforceFoundationSnapshot(BaseModel):
    operation_date: str
    summary: WorkforceFoundationSummary
    drivers: list[WorkforceDriverReadiness] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)

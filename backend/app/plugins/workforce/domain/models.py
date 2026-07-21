from enum import Enum

from pydantic import BaseModel, Field


class WorkforceValueOrigin(str, Enum):
    IMPORTED = "imported"
    MANUAL = "manual"


class WorkforceMember(BaseModel):
    workforce_member_id: int
    external_identifier: str
    display_name: str
    role: str | None = None
    employment_type: str | None = None
    contract_start: str | None = None
    contract_end: str | None = None
    weekly_hours: float | None = Field(default=None, ge=0)
    capabilities: list[str] = Field(default_factory=list)
    active: bool = True
    source_reference: str
    created_at: str
    updated_at: str


class WorkforceDayStatus(BaseModel):
    status_id: int
    workforce_member_id: int
    date: str
    status_code: str
    availability: bool
    shift_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    source_reference: str
    observed_or_confirmed: WorkforceValueOrigin
    updated_at: str


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
    absences_detected: int = Field(default=0, ge=0)
    excluded_rows: int = Field(default=0, ge=0)
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

from enum import Enum

from pydantic import BaseModel, Field


class OperationalCycleResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    NO_CYCLE_EVIDENCE = "NO_CYCLE_EVIDENCE"


class OperationalCycleReconciliationDetail(BaseModel):
    workbook_name: str
    workbook_driver_name: str | None = None
    transporter_id: str | None = None
    source_reference: str | None = None
    evidence_value: str | None = None
    proposed_cycle: str | None = None
    workforce_member_id: int | None = None
    workforce_external_identifier: str | None = None
    workforce_display_name: str | None = None
    current_cycle: str | None = None
    status: OperationalCycleResolutionStatus
    resolution_source: str | None = None
    apply_eligible: bool = False
    explanation: str


class OperationalCycleCoverageImpact(BaseModel):
    operational_date: str
    cycle: str
    segment: str | None = None
    station: str | None = None
    forecast_routes: int | None = None
    required_capacity: int | None = None
    assigned_before: int = Field(default=0, ge=0)
    assigned_after: int = Field(default=0, ge=0)


class OperationalCycleReconciliationSummary(BaseModel):
    workforce_total: int = Field(default=0, ge=0)
    currently_not_set: int = Field(default=0, ge=0)
    resolved_next_day: int = Field(default=0, ge=0)
    resolved_same_day: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)
    not_found: int = Field(default=0, ge=0)
    conflicts: int = Field(default=0, ge=0)
    no_cycle_evidence: int = Field(default=0, ge=0)
    unchanged_existing_cycles: int = Field(default=0, ge=0)
    apply_eligible: int = Field(default=0, ge=0)


class OperationalCycleReconciliationPreview(BaseModel):
    status: str
    workforce_import_id: int | None = None
    original_filename: str | None = None
    source_filename: str | None = None
    import_fingerprint: str | None = None
    cycle_source: str = "Planning.Turno"
    coverage_date_from: str = "2026-08-10"
    coverage_date_to: str = "2026-08-16"
    summary: OperationalCycleReconciliationSummary
    details: list[OperationalCycleReconciliationDetail] = Field(default_factory=list)
    coverage_impact: list[OperationalCycleCoverageImpact] = Field(default_factory=list)
    preview_fingerprint: str | None = None
    action_required: str


class OperationalCycleReconciliationResult(OperationalCycleReconciliationPreview):
    members_updated: int = Field(default=0, ge=0)
    audit_events_created: int = Field(default=0, ge=0)
    idempotent: bool = False

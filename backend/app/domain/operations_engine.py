from enum import Enum

from pydantic import BaseModel, Field

from app.domain.conflict_types import ConflictSeverity


class OperationalStatus(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class OperationalRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OperationalIssue(BaseModel):
    code: str
    severity: ConflictSeverity
    description: str
    reason: str
    entity_ref: str
    row_number: int | None = None
    suggested_action: str | None = None


class OperationalCapacity(BaseModel):
    routes: int = 0
    drivers: int = 0
    physical_vehicles: int = 0
    operational_vehicles: int = 0
    reserve_vehicles: int = 0
    blocked_vehicles: int = 0
    operational_margin: int = 0
    driver_margin: int = 0


class OperationalReadiness(BaseModel):
    status: OperationalStatus
    risk_level: OperationalRisk
    can_start_all_routes: bool
    operational_margin: int
    reserve_threshold: int
    critical_issues: int
    warning_issues: int
    reasons: list[str] = Field(default_factory=list)
    triggered_rules: list[str] = Field(default_factory=list)


class OperationalSummary(BaseModel):
    routes: int = 0
    drivers: int = 0
    physical_vehicles: int = 0
    operational_vehicles: int = 0
    reserve_vehicles: int = 0
    blocked_vehicles: int = 0
    issues_count: int = 0
    critical_issues: int = 0
    warning_issues: int = 0
    info_issues: int = 0


class OperationsDashboard(BaseModel):
    analysis_id: int | None = None
    generated_at: str
    summary: OperationalSummary
    issues: list[OperationalIssue] = Field(default_factory=list)
    capacity: OperationalCapacity
    readiness: OperationalReadiness

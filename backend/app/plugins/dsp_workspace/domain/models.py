from typing import Literal

from pydantic import BaseModel, Field


class SourceMetadata(BaseModel):
    available: bool
    status: str
    fetched_at: str
    partial: bool = False
    error: str | None = None


class PlanningMetadata(BaseModel):
    available: bool
    planning_id: int | None = None
    operation_date: str
    status: str | None = None
    source: str = "planning-operational"
    updated_at: str | None = None


class DriverProjection(BaseModel):
    planning_identifier: str | None = None
    workforce_member_id: int | None = None
    name: str | None = None


class VehicleProjection(BaseModel):
    planning_identifier: str | None = None
    fleet_asset_id: int | None = None
    plate: str | None = None
    model: str | None = None


class WorkforceProjection(BaseModel):
    availability_status: str | None = None
    convocable: bool | None = None
    reason: str | None = None
    contract: str | None = None
    station: str | None = None
    consecutivity_indicator: str | None = None


class FleetProjection(BaseModel):
    availability: str | None = None
    operational_status: str | None = None


JournalProcedureStatus = Literal[
    "completed",
    "missing",
    "pending",
    "not_expected",
    "unknown",
]


class JournalProjection(BaseModel):
    available: bool = True
    check_out_status: JournalProcedureStatus = "unknown"
    check_in_status: JournalProcedureStatus = "unknown"
    in_progress: bool = False
    anomaly: bool = False
    partial: bool = False


class DamageProjection(BaseModel):
    available: bool = True
    open_cases_count: int = 0
    highest_severity: str | None = None
    vehicle_blocked: bool = False
    relevant_case_ids: list[int] = Field(default_factory=list)
    partial: bool = False


AttentionCode = Literal[
    "DRIVER_WITHOUT_VEHICLE",
    "DRIVER_NOT_AVAILABLE",
    "VEHICLE_NOT_AVAILABLE",
    "JOURNAL_CHECKOUT_MISSING",
    "JOURNAL_CHECKIN_MISSING",
    "JOURNAL_ANOMALY",
    "JOURNAL_IN_PROGRESS",
    "OPEN_DAMAGE_CASE",
    "VEHICLE_BLOCKED_BY_DAMAGE",
    "HIGH_SEVERITY_DAMAGE",
]


class OperationalRow(BaseModel):
    assignment_id: int
    route: str | None = None
    wave: str | None = None
    driver: DriverProjection
    vehicle: VehicleProjection
    workforce: WorkforceProjection
    fleet: FleetProjection
    journal: JournalProjection = Field(default_factory=JournalProjection)
    damage: DamageProjection = Field(default_factory=DamageProjection)
    attention_codes: list[AttentionCode] = Field(default_factory=list)


class OperationalSignal(BaseModel):
    code: AttentionCode
    severity: Literal["info", "warning", "critical"]
    assignment_id: int
    workforce_member_id: int | None = None
    fleet_asset_id: int | None = None
    message: str
    source: Literal["planning", "workforce", "fleet", "journal", "damage"]


class DailyOperationsSnapshot(BaseModel):
    operation_date: str
    generated_at: str
    planning: PlanningMetadata
    sources: dict[
        Literal["planning", "workforce", "fleet", "journal", "damage"],
        SourceMetadata,
    ]
    rows: list[OperationalRow] = Field(default_factory=list)
    signals: list[OperationalSignal] = Field(default_factory=list)
    partial: bool = False

from enum import Enum

from pydantic import BaseModel, Field

from app.domain.assignment_models import Assignment


class PlanningStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    PARTIALLY_ASSIGNED = "partially_assigned"
    READY = "ready"
    CRITICAL = "critical"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class StationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlanningConfiguration(BaseModel):
    reserve_vehicle_threshold_global: int = Field(default=1, ge=0, le=1000)
    reserve_vehicle_threshold_by_station: dict[str, int] = Field(default_factory=dict)
    prefer_habitual_vehicle: bool = True
    preserve_imported_assignment: bool = True
    preserve_confirmed_manual_override: bool = True
    allow_cross_station_suggestion: bool = True
    maximum_assignments_per_driver: int = Field(default=1, ge=1, le=10)
    blocked_vehicle_statuses: list[str] = Field(
        default_factory=lambda: [
            "officina",
            "bloccato",
            "fermo",
            "non disponibile",
            "guasto",
            "manutenzione",
        ]
    )
    unrecognized_status_is_blocking: bool = True
    maximum_alternatives_per_assignment: int = Field(default=3, ge=0, le=10)

    def reserve_threshold_for(self, station: str) -> int:
        normalized = station.upper()
        for key, value in self.reserve_vehicle_threshold_by_station.items():
            if key.upper() == normalized:
                return value
        return self.reserve_vehicle_threshold_global


class OperationalPlanning(BaseModel):
    id: int | None = None
    operation_date: str
    station: str | None = None
    source_planning_import_id: int
    source_fleet_import_id: int
    status: PlanningStatus = PlanningStatus.DRAFT
    version: int = 1
    reserve_threshold: int = 1
    configuration: PlanningConfiguration
    created_at: str
    updated_at: str


class PlanningConflict(BaseModel):
    code: str
    severity: str
    message: str
    entity_ref: str
    blocking: bool = False
    suggested_action: str | None = None


class PlanningSummary(BaseModel):
    routes_total: int = 0
    routes_assigned: int = 0
    routes_unassigned: int = 0
    assignments_confirmed: int = 0
    manual_overrides: int = 0
    drivers_used: int = 0
    vehicles_used: int = 0
    stations: int = 0
    critical_conflicts: int = 0
    warnings: int = 0


class DriverResource(BaseModel):
    id: str
    name: str
    station: str
    habitual_plate: str | None = None


class VehicleResource(BaseModel):
    id: str
    plate: str
    station: str
    state: str
    habitual_driver_id: str | None = None


class CrossStationSuggestion(BaseModel):
    from_station: str
    to_station: str
    plate: str
    source_margin_before: int
    source_margin_after: int
    target_deficit_before: int
    reason: str
    applied: bool = False


class StationCapacity(BaseModel):
    station: str
    routes_total: int
    drivers_available: int
    drivers_assigned: int
    drivers_unused: int
    physical_vehicles: int
    operational_vehicles: int
    assigned_vehicles: int
    free_vehicles: int
    safe_reserve_vehicles: int
    blocked_vehicles: int
    deficit_or_surplus: int
    operational_margin: int
    reserve_threshold: int
    readiness: StationRisk
    issues: list[str] = Field(default_factory=list)
    cross_station_suggestions: list[CrossStationSuggestion] = Field(default_factory=list)


class GenerationMetadata(BaseModel):
    generated_at: str
    rules_version: str = "assignment-v1"
    planning_import_id: int
    fleet_import_id: int
    operation_date_source: str
    applied_rules: list[str] = Field(default_factory=list)
    skipped_rules: list[str] = Field(default_factory=list)


class PlanningBundle(BaseModel):
    planning: OperationalPlanning
    summary: PlanningSummary
    assignments: list[Assignment] = Field(default_factory=list)
    unassigned_routes: list[str] = Field(default_factory=list)
    unused_drivers: list[DriverResource] = Field(default_factory=list)
    available_vehicles: list[VehicleResource] = Field(default_factory=list)
    reserve_vehicles: list[VehicleResource] = Field(default_factory=list)
    station_capacity: list[StationCapacity] = Field(default_factory=list)
    conflicts: list[PlanningConflict] = Field(default_factory=list)
    generation_metadata: GenerationMetadata
    history: dict[str, list[dict[str, object]]] = Field(
        default_factory=lambda: {"versions": [], "events": []}
    )

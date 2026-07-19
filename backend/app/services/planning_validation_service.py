from collections import Counter

from app.domain.assignment_rules import (
    OPERATIONAL_VEHICLE_STATUSES,
    RESERVE_VEHICLE_STATUSES,
    is_valid_plate,
    station_key,
)
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.planning_models import PlanningConflict
from app.utils.text_normalizer import normalize_text


class PlanningValidationError(ValueError):
    def __init__(
        self,
        message: str,
        code: str = "PLANNING_VALIDATION_ERROR",
        conflicts: list[PlanningConflict] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.conflicts = conflicts or []


def validate_generation_inputs(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
    station_filter: str | None,
    blocked_statuses: list[str],
) -> list[PlanningConflict]:
    if not planning_rows:
        raise PlanningValidationError(
            "Il planning importato non contiene righe utilizzabili.",
            code="EMPTY_PLANNING",
        )
    if not fleet_rows:
        raise PlanningValidationError(
            "Il parco auto importato non contiene righe utilizzabili.",
            code="EMPTY_FLEET",
        )

    conflicts: list[PlanningConflict] = []
    missing_routes = [row.row_number for row in planning_rows if not row.route]
    if missing_routes:
        blocking = PlanningConflict(
            code="MISSING_ROUTE_ID",
            severity="critical",
            message=f"{len(missing_routes)} righe non hanno un identificativo rotta.",
            entity_ref=",".join(str(item) for item in missing_routes),
            blocking=True,
            suggested_action="Completa gli identificativi rotta nel file sorgente.",
        )
        raise PlanningValidationError(
            blocking.message,
            code=blocking.code,
            conflicts=[blocking],
        )

    route_counts = Counter(row.route for row in planning_rows if row.route)
    duplicate_routes = sorted(route for route, count in route_counts.items() if count > 1)
    if duplicate_routes:
        conflict = PlanningConflict(
            code="DUPLICATE_ROUTE",
            severity="critical",
            message="Sono presenti identificativi rotta duplicati.",
            entity_ref=", ".join(duplicate_routes),
            blocking=True,
            suggested_action="Mantieni una sola riga per route_id.",
        )
        raise PlanningValidationError(
            conflict.message,
            code=conflict.code,
            conflicts=[conflict],
        )

    planning_stations = {station_key(row.station) for row in planning_rows if row.station}
    fleet_stations = {station_key(row.station) for row in fleet_rows if row.station}
    if station_filter:
        requested = station_key(station_filter)
        if requested not in planning_stations or requested not in fleet_stations:
            raise PlanningValidationError(
                f"La station '{station_filter}' non è presente in entrambi gli import.",
                code="INCOMPATIBLE_STATION",
            )
    elif planning_stations and fleet_stations and not planning_stations.intersection(fleet_stations):
        raise PlanningValidationError(
            "Planning e parco auto non condividono alcuna station.",
            code="INCOMPATIBLE_STATIONS",
        )

    driver_counts = Counter(
        row.driver_key for row in planning_rows if row.driver_key
    )
    for driver_id, count in driver_counts.items():
        if count > 1:
            conflicts.append(
                PlanningConflict(
                    code="DUPLICATE_DRIVER",
                    severity="critical",
                    message="Driver presente su più rotte.",
                    entity_ref=driver_id,
                    blocking=False,
                    suggested_action="Lascia un solo incarico oppure modifica manualmente la seconda rotta.",
                )
            )

    plate_counts = Counter(row.vehicle_plate for row in fleet_rows if row.vehicle_plate)
    for plate, count in plate_counts.items():
        if count > 1:
            conflicts.append(
                PlanningConflict(
                    code="DUPLICATE_VEHICLE",
                    severity="critical",
                    message="La stessa targa compare più volte nel parco auto.",
                    entity_ref=plate,
                    blocking=False,
                    suggested_action="Conferma quale record rappresenta lo stato corrente del mezzo.",
                )
            )

    blocked_terms = {normalize_text(item) for item in blocked_statuses}
    recognized = OPERATIONAL_VEHICLE_STATUSES | RESERVE_VEHICLE_STATUSES | blocked_terms
    for row in fleet_rows:
        if not is_valid_plate(row.vehicle_plate):
            conflicts.append(
                PlanningConflict(
                    code="INVALID_VEHICLE_PLATE",
                    severity="critical",
                    message="Mezzo con targa non valida escluso dalle assegnazioni.",
                    entity_ref=f"fleet:{row.row_number}",
                    blocking=False,
                    suggested_action="Correggi la targa nel file del parco auto.",
                )
            )
        status = normalize_text(row.status)
        workshop = normalize_text(row.workshop)
        status_is_blocked = any(term and term in status for term in blocked_terms)
        workshop_is_blocked = any(term and term in workshop for term in blocked_terms)
        if not status_is_blocked and not workshop_is_blocked and status not in recognized:
            conflicts.append(
                PlanningConflict(
                    code="UNRECOGNIZED_VEHICLE_STATUS",
                    severity="warning",
                    message="Stato mezzo non riconosciuto: il mezzo sarà bloccato.",
                    entity_ref=row.vehicle_plate or f"fleet:{row.row_number}",
                    blocking=False,
                    suggested_action="Conferma manualmente lo stato prima di usare il mezzo.",
                )
            )

    return conflicts

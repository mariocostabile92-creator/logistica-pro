from dataclasses import dataclass

from app.plugins.dsp_workspace.domain.models import (
    CoverageProjection,
    DailyOperationsCounts,
    DailyOperationsWarning,
    DriverProjection,
    FleetProjection,
    OperationalRow,
    VehicleProjection,
    WorkforceProjection,
)
from app.plugins.workforce.domain.coverage import DailyCoverageResponse
from app.plugins.workforce.domain.operational_status import (
    ABSENCE_STATUS_CODES,
    NON_OPERATIONAL_STATUS_CODES,
)


ABSENCE_STATUSES = ABSENCE_STATUS_CODES
NON_OPERATIONAL_STATUSES = NON_OPERATIONAL_STATUS_CODES


@dataclass(frozen=True)
class WorkforceBridgeResult:
    rows: list[OperationalRow]
    counts: DailyOperationsCounts
    warnings: list[DailyOperationsWarning]


def _normalized(value: object) -> str:
    return str(value or "").strip()


def _is_planned(record: dict[str, object]) -> bool:
    status = _normalized(record.get("status_code")).casefold()
    has_assignment = bool(
        _normalized(record.get("shift_code"))
        or _normalized(record.get("operational_activity"))
    )
    return (
        bool(record.get("availability"))
        and status not in NON_OPERATIONAL_STATUSES
        and has_assignment
    )


def _availability_reason(status: str) -> str:
    return {
        "holiday": "Ferie.",
        "sickness": "Malattia.",
        "leave": "Permesso.",
        "rest": "Riposo pianificato.",
        "unavailable": "Indisponibilita dichiarata.",
    }.get(status, "Assegnazione Workforce disponibile.")


def build_workforce_bridge(
    records: list[dict[str, object]],
) -> WorkforceBridgeResult:
    planned = [record for record in records if _is_planned(record)]
    rows = [
        OperationalRow(
            assignment_id=int(record["status_id"]),
            route=(
                _normalized(record.get("operational_activity"))
                or _normalized(record.get("shift_code"))
                or None
            ),
            driver=DriverProjection(
                planning_identifier=_normalized(record.get("external_identifier")) or None,
                workforce_member_id=int(record["workforce_member_id"]),
                name=_normalized(record.get("display_name")) or None,
            ),
            vehicle=VehicleProjection(),
            workforce=WorkforceProjection(
                availability_status=_normalized(record.get("status_code")) or None,
                convocable=bool(record.get("availability")),
                reason=_availability_reason(
                    _normalized(record.get("status_code")).casefold()
                ),
                contract=_normalized(record.get("employment_type")) or None,
                station=_normalized(record.get("station")) or None,
            ),
            fleet=FleetProjection(),
        )
        for record in planned
    ]
    cycle_not_set = sum(
        _normalized(record.get("operational_cycle")).upper() == "NOT_SET"
        for record in planned
    )
    warnings = []
    if cycle_not_set:
        warnings.append(DailyOperationsWarning(
            code="OPERATIONAL_CYCLE_NOT_SET",
            severity="warning",
            message=(
                f"{cycle_not_set} driver pianificati non hanno il ciclo operativo impostato."
            ),
        ))
    return WorkforceBridgeResult(
        rows=rows,
        counts=DailyOperationsCounts(
            driver_planned_count=len(planned),
            driver_available_count=sum(
                bool(record.get("availability"))
                and _normalized(record.get("status_code")).casefold()
                not in NON_OPERATIONAL_STATUSES
                for record in records
            ),
            driver_absent_count=sum(
                _normalized(record.get("status_code")).casefold()
                in ABSENCE_STATUSES
                for record in records
            ),
            reserve_count=sum(bool(record.get("is_reserve")) for record in planned),
        ),
        warnings=warnings,
    )


def coverage_projection(
    response: DailyCoverageResponse,
) -> tuple[list[CoverageProjection], list[DailyOperationsWarning]]:
    projections: list[CoverageProjection] = []
    warnings: list[DailyOperationsWarning] = []
    for item in response.items:
        projection = CoverageProjection(
            cycle=item.cycle,
            segment=item.segment,
            station=item.station,
            forecast=item.forecast_routes,
            requirement=item.required_capacity,
            assigned=item.assigned_drivers,
            forecast_gap=item.forecast_gap,
            requirement_gap=item.requirement_gap,
            reserve=item.reserve_drivers,
            status=item.coverage_status.value,
        )
        projections.append(projection)
        label = item.cycle if not item.segment else f"{item.cycle} {item.segment}"
        if item.coverage_status.value == "NO_FORECAST":
            warnings.append(DailyOperationsWarning(
                code="FORECAST_MISSING",
                severity="info",
                message=f"Forecast non disponibile per {label}.",
                cycle=item.cycle,
                segment=item.segment,
            ))
        elif (item.forecast_gap or 0) > 0:
            warnings.append(DailyOperationsWarning(
                code="FORECAST_NOT_COVERED",
                severity="critical",
                message=(
                    f"{label}: mancano {item.forecast_gap} driver sul forecast."
                ),
                cycle=item.cycle,
                segment=item.segment,
            ))
        elif (item.requirement_gap or 0) > 0:
            warnings.append(DailyOperationsWarning(
                code="REQUIREMENT_NOT_COVERED",
                severity="warning",
                message=(
                    f"{label}: mancano {item.requirement_gap} driver per il requisito."
                ),
                cycle=item.cycle,
                segment=item.segment,
            ))
    return projections, warnings


def has_coverage_data(items: list[CoverageProjection]) -> bool:
    return any(item.forecast is not None or item.assigned > 0 for item in items)

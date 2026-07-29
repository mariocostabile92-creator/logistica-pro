from collections import Counter, defaultdict

from app.domain.core_language import (
    DriverMapper,
    RouteMapper,
    StationMapper,
    VehicleMapper,
)
from app.domain.conflict_types import ConflictCode, ConflictSeverity
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow, OperationConflict
from app.utils.text_normalizer import compact_key, normalize_text


UNAVAILABLE_STATUS = {"officina", "bloccato", "fermo", "non disponibile", "guasto", "manutenzione"}
CONFLICT_REASONS = {
    ConflictCode.UNKNOWN_DRIVER: "Il driver del planning non corrisponde a nessun driver normalizzato nel parco auto.",
    ConflictCode.UNKNOWN_VEHICLE: "La targa assegnata nel planning non corrisponde a nessun mezzo importato.",
    ConflictCode.VEHICLE_MULTI_DRIVER: "La stessa targa compare su rotte associate a driver diversi.",
    ConflictCode.DRIVER_MULTI_ROUTE: "Lo stesso driver normalizzato compare su più rotte nello stesso planning.",
    ConflictCode.UNAVAILABLE_VEHICLE_ASSIGNED: "Lo stato o l'officina del mezzo indicano che non è disponibile alla partenza.",
    ConflictCode.DRIVER_WITHOUT_VEHICLE: "La riga contiene un driver riconosciuto ma non una targa valida.",
    ConflictCode.ROUTE_WITHOUT_DRIVER: "La rotta non contiene un driver riconoscibile.",
    ConflictCode.INVALID_VEHICLE_PLATE: "Il record del parco non contiene una targa che possa identificare il mezzo.",
    ConflictCode.DUPLICATE_ROW: "Due o più righe del planning hanno gli stessi valori originali.",
    ConflictCode.UNKNOWN_STATION: "La station normalizzata non è inclusa nell'elenco di station riconosciute.",
    ConflictCode.INSUFFICIENT_OPERATIONAL_VEHICLES: "Le rotte superano il numero di mezzi non bloccati disponibili.",
    ConflictCode.LOW_RESERVE_MARGIN: "Il numero di mezzi oltre il fabbisogno rotte è inferiore alla soglia configurata.",
}


def _task_identifier(row: NormalizedPlanningRow) -> str:
    legacy_route = row.route or f"row-{row.row_number}"
    task = RouteMapper.to_core(legacy_route)
    return task.external_identifier if task else legacy_route


def _human_resource_identifier(value: str | None) -> str | None:
    resource = DriverMapper.to_core(value)
    return resource.external_identifier if resource else None


def _asset_identifier(value: str | None) -> str | None:
    asset = VehicleMapper.to_core(value)
    return asset.external_identifier if asset else None


def _operational_unit_identifier(value: str | None) -> str | None:
    unit = StationMapper.to_core(value)
    return unit.external_identifier if unit else None


def _conflict(
    code: ConflictCode,
    severity: ConflictSeverity,
    message: str,
    entity_ref: str,
    row_number: int | None = None,
    suggested_action: str | None = None,
) -> OperationConflict:
    return OperationConflict(
        code=code.value,
        severity=severity.value,
        message=message,
        reason=CONFLICT_REASONS[code],
        entity_ref=entity_ref,
        row_number=row_number,
        suggested_action=suggested_action,
    )


def is_operational_vehicle(row: NormalizedFleetRow) -> bool:
    status = normalize_text(row.status)
    workshop = normalize_text(row.workshop)
    return bool(row.vehicle_plate) and not any(term in status or term in workshop for term in UNAVAILABLE_STATUS)


def detect_conflicts(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
    reserve_threshold: int = 1,
    recognized_operational_units: set[str] | None = None,
) -> list[OperationConflict]:
    conflicts: list[OperationConflict] = []
    recognized_units = {
        compact_key(unit)
        for unit in (recognized_operational_units or set())
    }
    fleet_by_plate = {
        asset_identifier: row
        for row in fleet_rows
        if (asset_identifier := _asset_identifier(row.vehicle_plate))
    }
    fleet_driver_keys = {
        resource_identifier
        for row in fleet_rows
        for key in (row.driver_key, row.second_driver_key)
        if (
            resource_identifier := _human_resource_identifier(key)
        )
    }
    operational_plates = {
        asset_identifier
        for row in fleet_rows
        if is_operational_vehicle(row)
        if (
            asset_identifier := _asset_identifier(row.vehicle_plate)
        )
    }

    route_values = [
        _task_identifier(row)
        for row in planning_rows
    ]
    raw_signatures = Counter(
        tuple(sorted((key, str(value)) for key, value in row.raw.items()))
        for row in planning_rows
    )
    for row in planning_rows:
        signature = tuple(sorted((key, str(value)) for key, value in row.raw.items()))
        if raw_signatures[signature] > 1:
            conflicts.append(_conflict(
                ConflictCode.DUPLICATE_ROW,
                ConflictSeverity.WARNING,
                "Riga planning duplicata.",
                f"planning:{row.row_number}",
                row.row_number,
                "Verifica se la rotta è stata caricata due volte.",
            ))

    for row in fleet_rows:
        if not row.vehicle_plate:
            conflicts.append(_conflict(
                ConflictCode.INVALID_VEHICLE_PLATE,
                ConflictSeverity.CRITICAL,
                "Mezzo senza targa valida nel parco auto.",
                f"fleet:{row.row_number}",
                row.row_number,
                "Correggi o completa la targa prima dell'analisi operativa.",
            ))

    for row in planning_rows:
        driver_identifier = _human_resource_identifier(row.driver_key)
        asset_identifier = _asset_identifier(row.vehicle_plate)
        unit_identifier = _operational_unit_identifier(row.station)
        if not driver_identifier:
            conflicts.append(_conflict(
                ConflictCode.ROUTE_WITHOUT_DRIVER,
                ConflictSeverity.CRITICAL,
                f"Rotta '{row.route or row.row_number}' senza driver riconosciuto.",
                row.route or f"planning:{row.row_number}",
                row.row_number,
                "Completa o conferma il driver prima della partenza.",
            ))
        if (
            driver_identifier
            and driver_identifier not in fleet_driver_keys
        ):
            conflicts.append(_conflict(
                ConflictCode.UNKNOWN_DRIVER,
                ConflictSeverity.WARNING,
                f"Driver '{row.driver_name}' presente nel planning ma non riconosciuto nel parco.",
                row.driver_name or f"planning:{row.row_number}",
                row.row_number,
                "Conferma alias del driver o aggiorna il parco auto.",
            ))
        if (
            asset_identifier
            and asset_identifier not in fleet_by_plate
        ):
            conflicts.append(_conflict(
                ConflictCode.UNKNOWN_VEHICLE,
                ConflictSeverity.CRITICAL,
                f"Mezzo '{row.vehicle_plate}' presente nel planning ma non nel parco auto.",
                row.vehicle_plate,
                row.row_number,
                "Verifica la targa o aggiungi il mezzo al parco.",
            ))
        if driver_identifier and not asset_identifier:
            conflicts.append(_conflict(
                ConflictCode.DRIVER_WITHOUT_VEHICLE,
                ConflictSeverity.CRITICAL,
                f"Driver '{row.driver_name or '-'}' senza mezzo assegnato.",
                row.driver_name or f"planning:{row.row_number}",
                row.row_number,
                "Assegna un mezzo valido prima della partenza.",
            ))
        if (
            asset_identifier
            and asset_identifier in fleet_by_plate
            and asset_identifier not in operational_plates
        ):
            conflicts.append(_conflict(
                ConflictCode.UNAVAILABLE_VEHICLE_ASSIGNED,
                ConflictSeverity.CRITICAL,
                f"Mezzo '{row.vehicle_plate}' non disponibile ma assegnato.",
                row.vehicle_plate,
                row.row_number,
                "Sostituisci il mezzo o aggiorna lo stato se è tornato operativo.",
            ))
        if (
            unit_identifier
            and recognized_units
            and compact_key(unit_identifier) not in recognized_units
        ):
            conflicts.append(_conflict(
                ConflictCode.UNKNOWN_STATION,
                ConflictSeverity.INFO,
                f"Station '{row.station}' non riconosciuta.",
                row.station,
                row.row_number,
                "Conferma manualmente la station o aggiungila agli alias.",
            ))

    drivers_to_routes: dict[str, set[str]] = defaultdict(set)
    plates_to_drivers: dict[str, set[str]] = defaultdict(set)
    for row in planning_rows:
        driver_identifier = _human_resource_identifier(row.driver_key)
        asset_identifier = _asset_identifier(row.vehicle_plate)
        if driver_identifier:
            drivers_to_routes[driver_identifier].add(
                _task_identifier(row)
            )
        if asset_identifier and driver_identifier:
            plates_to_drivers[asset_identifier].add(
                driver_identifier
            )

    for driver_key, routes in drivers_to_routes.items():
        if len(routes) > 1:
            conflicts.append(_conflict(
                ConflictCode.DRIVER_MULTI_ROUTE,
                ConflictSeverity.CRITICAL,
                "Driver assegnato a più rotte nello stesso dataset.",
                driver_key,
                None,
                "Mantieni una sola rotta o dividi esplicitamente il turno.",
            ))
    for plate, drivers in plates_to_drivers.items():
        if len(drivers) > 1:
            conflicts.append(_conflict(
                ConflictCode.VEHICLE_MULTI_DRIVER,
                ConflictSeverity.CRITICAL,
                f"Mezzo '{plate}' assegnato a più driver.",
                plate,
                None,
                "Riassegna il mezzo o verifica eventuale doppio turno.",
            ))

    routes_count = len(set(route_values))
    operational_count = len(operational_plates)
    reserve_margin = operational_count - routes_count
    if operational_count < routes_count:
        conflicts.append(_conflict(
            ConflictCode.INSUFFICIENT_OPERATIONAL_VEHICLES,
            ConflictSeverity.CRITICAL,
            "Numero di mezzi operativi inferiore al numero di rotte.",
            "capacity",
            None,
            "Riduci rotte, recupera mezzi o pianifica sostituzioni.",
        ))
    elif reserve_margin < reserve_threshold:
        conflicts.append(_conflict(
            ConflictCode.LOW_RESERVE_MARGIN,
            ConflictSeverity.WARNING,
            "Margine di scorta mezzi sotto la soglia configurata.",
            "capacity",
            None,
            "Aumenta mezzi disponibili o abbassa consapevolmente la soglia.",
        ))

    return conflicts


def analyze_operations(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
    reserve_threshold: int = 1,
    recognized_operational_units: set[str] | None = None,
):
    from app.services.operations_engine import (
        dashboard_to_legacy_analysis,
        evaluate_operations,
    )

    dashboard = evaluate_operations(
        planning_rows,
        fleet_rows,
        reserve_threshold,
        recognized_operational_units,
    )
    return dashboard_to_legacy_analysis(dashboard)

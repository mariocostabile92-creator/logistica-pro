from dataclasses import dataclass

from app.plugins.dsp_workspace.domain.models import (
    DriverProjection,
    FleetProjection,
    OperationalRow,
    OperationalSignal,
    VehicleProjection,
    WorkforceProjection,
)
from app.plugins.fleet.application.planning_input_producer import (
    AVAILABLE_ASSET_STATES,
)
from app.plugins.fleet.journal.control_room.planning_vehicle_adapter import (
    assignment_is_active,
    fleet_asset_for_assignment,
    index_fleet_assets_by_plate,
)
from app.plugins.workforce.application.driver_identity_resolver import (
    resolve_driver_identity,
)
from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolutionStatus,
)


@dataclass(frozen=True)
class RowBuildResult:
    rows: list[OperationalRow]
    signals: list[OperationalSignal]
    unresolved_drivers: int = 0
    unresolved_vehicles: int = 0


def _signal(**values) -> OperationalSignal:
    return OperationalSignal(**values)


def build_operational_rows(
    *,
    organization_id: str,
    planning_snapshot: dict | None,
    workforce_drivers: dict[int, object],
    fleet_assets: list[dict],
) -> RowBuildResult:
    assets_by_plate = index_fleet_assets_by_plate(fleet_assets)
    rows: list[OperationalRow] = []
    signals: list[OperationalSignal] = []
    unresolved_drivers = 0
    unresolved_vehicles = 0
    assignments = planning_snapshot.get("assignments", []) if planning_snapshot else []
    assignments = sorted(
        (item for item in assignments if assignment_is_active(item)),
        key=lambda item: (
            str(item.get("route_id") or "").casefold(),
            int(item["id"]),
        ),
    )

    for assignment in assignments:
        assignment_id = int(assignment["id"])
        driver_identifier = str(assignment.get("driver_id") or "").strip() or None
        driver_name = str(assignment.get("driver_name") or "").strip() or None
        member_id: int | None = None
        workforce_driver = None
        if driver_identifier:
            resolution = resolve_driver_identity(
                organization_id=organization_id,
                driver_identifier=driver_identifier,
                source="planning",
            )
            if resolution.status is DriverIdentityResolutionStatus.MATCH:
                member_id = resolution.workforce_member_id
                driver_name = resolution.display_name
                workforce_driver = workforce_drivers.get(member_id)
            else:
                unresolved_drivers += 1

        asset = fleet_asset_for_assignment(assignment, assets_by_plate)
        asset_id = int(asset["id"]) if asset else None
        vehicle_identifier = (
            str(assignment.get("vehicle_id") or assignment.get("plate") or "").strip()
            or None
        )
        if vehicle_identifier and not asset:
            unresolved_vehicles += 1

        attention_codes: list[str] = []
        if (driver_identifier or driver_name) and asset_id is None:
            attention_codes.append("DRIVER_WITHOUT_VEHICLE")
            signals.append(_signal(
                code="DRIVER_WITHOUT_VEHICLE",
                severity="critical",
                assignment_id=assignment_id,
                workforce_member_id=member_id,
                fleet_asset_id=None,
                message="Driver assegnato senza un mezzo Fleet valido.",
                source="planning",
            ))
        if workforce_driver is not None and not workforce_driver.callable:
            attention_codes.append("DRIVER_NOT_AVAILABLE")
            signals.append(_signal(
                code="DRIVER_NOT_AVAILABLE",
                severity="critical",
                assignment_id=assignment_id,
                workforce_member_id=member_id,
                fleet_asset_id=asset_id,
                message=workforce_driver.callability_reason,
                source="workforce",
            ))
        if asset is not None and asset.get("availability") not in AVAILABLE_ASSET_STATES:
            attention_codes.append("VEHICLE_NOT_AVAILABLE")
            signals.append(_signal(
                code="VEHICLE_NOT_AVAILABLE",
                severity="critical",
                assignment_id=assignment_id,
                workforce_member_id=member_id,
                fleet_asset_id=asset_id,
                message="Il mezzo assegnato non risulta operativo.",
                source="fleet",
            ))

        rows.append(OperationalRow(
            assignment_id=assignment_id,
            route=assignment.get("route_id"),
            wave=assignment.get("cycle_or_wave"),
            driver=DriverProjection(
                planning_identifier=driver_identifier,
                workforce_member_id=member_id,
                name=driver_name,
            ),
            vehicle=VehicleProjection(
                planning_identifier=vehicle_identifier,
                fleet_asset_id=asset_id,
                plate=(str(asset.get("plate") or "") or None) if asset else None,
                model=(str(asset.get("category") or "") or None) if asset else None,
            ),
            workforce=WorkforceProjection(
                availability_status=(
                    workforce_driver.availability_status if workforce_driver else None
                ),
                convocable=(workforce_driver.callable if workforce_driver else None),
                reason=(
                    workforce_driver.callability_reason if workforce_driver else None
                ),
                contract=(workforce_driver.contract if workforce_driver else None),
                station=(workforce_driver.station if workforce_driver else None),
                consecutivity_indicator=(
                    workforce_driver.consecutivity_status if workforce_driver else None
                ),
            ),
            fleet=FleetProjection(
                availability=asset.get("availability") if asset else None,
                operational_status=asset.get("availability") if asset else None,
            ),
            attention_codes=attention_codes,
        ))

    return RowBuildResult(
        rows=rows,
        signals=signals,
        unresolved_drivers=unresolved_drivers,
        unresolved_vehicles=unresolved_vehicles,
    )


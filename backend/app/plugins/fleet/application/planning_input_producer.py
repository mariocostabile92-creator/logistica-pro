from collections.abc import Sequence
from datetime import date, datetime, timedelta

from app.domain.core_language import (
    AssetReference,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
)
from app.domain.planning_inputs import (
    FleetPlanningInput,
    PlanningAssetRegistry,
    PlanningInputScope,
    PlanningInputSnapshot,
    PlanningInputType,
    PlanningResourceCapability,
    build_planning_input_snapshot,
)
from app.plugins.fleet.domain.models import Asset
from app.plugins.fleet.infrastructure import repository


AVAILABLE_ASSET_STATES = frozenset({
    "available", "reserve", "disponibile", "disponibile_con_limitazioni",
})


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Fleet timestamps must be timezone-aware.")
    return parsed


def build_fleet_planning_input_snapshot(
    *,
    organization_id: str,
    operational_unit: OperationalUnit,
    operation_date: date,
    assets: Sequence[Asset],
    assessed_at: datetime,
    freshness_ttl: timedelta,
) -> PlanningInputSnapshot:
    scope = PlanningInputScope(
        organization_id=organization_id,
        operational_unit=operational_unit,
        operation_date=operation_date,
    )
    ordered_assets = sorted(
        assets,
        key=lambda item: item.external_identifier,
    )
    payload = FleetPlanningInput(
        registry=PlanningAssetRegistry(
            assets=tuple(
                AssetReference(
                    external_identifier=item.external_identifier,
                    category=item.category,
                )
                for item in ordered_assets
            )
        ),
        availability=tuple(
            ResourceAvailability(
                resource_identifier=item.external_identifier,
                resource_kind=ResourceKind.ASSET,
                available=(
                    item.availability in AVAILABLE_ASSET_STATES
                ),
                observed_state=item.availability,
                reason=item.operational_status_reason,
                origin=item.operational_status_origin,
            )
            for item in ordered_assets
        ),
        capabilities=tuple(
            PlanningResourceCapability(
                resource_identifier=item.external_identifier,
                resource_kind=ResourceKind.ASSET,
                capability=capability,
            )
            for item in ordered_assets
            for capability in sorted(set(item.capabilities))
        ),
    )
    observed_at = max(
        (_timestamp(item.updated_at) for item in ordered_assets),
        default=assessed_at,
    )
    return build_planning_input_snapshot(
        input_type=PlanningInputType.FLEET,
        producer="fleet-plugin",
        contract_name="fleet-planning-input",
        scope=scope,
        payload=payload,
        observed_at=observed_at,
        assessed_at=assessed_at,
        freshness_ttl=freshness_ttl,
    )


def produce_fleet_planning_input_snapshot(
    *,
    organization_id: str,
    operational_unit: OperationalUnit,
    operation_date: date,
    assessed_at: datetime,
    freshness_ttl: timedelta,
) -> PlanningInputSnapshot:
    return build_fleet_planning_input_snapshot(
        organization_id=organization_id,
        operational_unit=operational_unit,
        operation_date=operation_date,
        assets=repository.list_assets(),
        assessed_at=assessed_at,
        freshness_ttl=freshness_ttl,
    )

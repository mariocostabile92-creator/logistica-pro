from datetime import datetime, timedelta

from app.domain.planning_inputs.fingerprints import (
    planning_input_fingerprint,
)
from app.domain.planning_inputs.models import (
    PLANNING_INPUT_CONTRACT_VERSION,
    PlanningInputContract,
    PlanningInputFreshness,
    PlanningInputMetadata,
    PlanningInputPayload,
    PlanningInputProvenance,
    PlanningInputScope,
    PlanningInputSnapshot,
    PlanningInputSource,
    PlanningInputType,
    PlanningInputVersion,
)
from app.domain.planning_inputs.validation import (
    create_planning_input_snapshot,
)


def build_planning_input_snapshot(
    *,
    input_type: PlanningInputType,
    producer: str,
    contract_name: str,
    scope: PlanningInputScope,
    payload: PlanningInputPayload,
    observed_at: datetime,
    assessed_at: datetime,
    freshness_ttl: timedelta,
) -> PlanningInputSnapshot:
    if freshness_ttl <= timedelta(0):
        raise ValueError("freshness_ttl must be positive.")
    fingerprint = planning_input_fingerprint(scope, payload)
    source_reference = f"{producer}:{fingerprint}"
    contract = PlanningInputContract(
        metadata=PlanningInputMetadata(
            input_type=input_type,
            source=PlanningInputSource(
                producer=producer,
                contract_name=contract_name,
                contract_version=PLANNING_INPUT_CONTRACT_VERSION,
                source_reference=source_reference,
                provenance=PlanningInputProvenance.CORE_PROJECTION,
                produced_at=assessed_at,
            ),
            scope=scope,
            version=PlanningInputVersion(value=fingerprint),
            freshness=PlanningInputFreshness(
                observed_at=observed_at,
                expires_at=observed_at + freshness_ttl,
            ),
        ),
        payload=payload,
    )
    return create_planning_input_snapshot(
        contract,
        assessed_at,
        snapshot_id=(
            f"{input_type.value}:{scope.organization_id}:"
            f"{scope.operational_unit.external_identifier}:"
            f"{scope.operation_date.isoformat()}:{fingerprint[:16]}"
        ),
    )

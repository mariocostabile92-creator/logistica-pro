from datetime import datetime

from app.domain.planning_inputs.fingerprints import (
    planning_input_envelope_fingerprint,
)
from app.domain.planning_inputs.models import (
    PlanningInputEnvelope,
    PlanningInputSnapshot,
    PlanningInputType,
    PlanningInputVersion,
)


def _require_input_type(
    snapshot: PlanningInputSnapshot,
    expected: PlanningInputType,
) -> None:
    actual = snapshot.contract.metadata.input_type
    if actual is not expected:
        raise ValueError(
            f"Expected a {expected.value} snapshot, received {actual.value}."
        )


def compose_planning_input_envelope(
    workforce: PlanningInputSnapshot,
    fleet: PlanningInputSnapshot,
    *,
    created_at: datetime,
) -> PlanningInputEnvelope:
    _require_input_type(workforce, PlanningInputType.WORKFORCE)
    _require_input_type(fleet, PlanningInputType.FLEET)
    snapshots = (workforce, fleet)
    scope = workforce.contract.metadata.scope
    fingerprint = planning_input_envelope_fingerprint(scope, snapshots)
    return PlanningInputEnvelope(
        envelope_id=(
            f"planning-input:{scope.organization_id}:"
            f"{scope.operational_unit.external_identifier}:"
            f"{scope.operation_date.isoformat()}:{fingerprint[:16]}"
        ),
        scope=scope,
        version=PlanningInputVersion(value=fingerprint),
        created_at=created_at,
        snapshots=snapshots,
        dependencies=tuple(
            item
            for snapshot in snapshots
            for item in snapshot.contract.dependencies
        ),
    )

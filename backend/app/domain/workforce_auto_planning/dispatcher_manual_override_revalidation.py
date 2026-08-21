from app.domain.workforce_auto_planning.dispatcher_manual_override import (
    DispatcherManualOverride,
    DispatcherOverrideOperationType,
)
from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
)
from app.domain.workforce_auto_planning.operational_demand import OperationalDemand
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.workforce_eligibility_evaluator import (
    evaluate_workforce_candidate_eligibility,
)


class DispatcherManualOverrideRevalidationError(ValueError):
    pass


class DispatcherManualOverrideDemandNotFoundError(
    DispatcherManualOverrideRevalidationError
):
    pass


class DispatcherManualOverrideCandidateNotFoundError(
    DispatcherManualOverrideRevalidationError
):
    pass


def _validate_authoritative_scope(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    previous: ComposedWeeklyWorkforceProposal,
    override: DispatcherManualOverride,
) -> None:
    proposal = previous.proposal
    if (
        snapshot.organization_id != proposal.organization_id
        or override.organization_id != proposal.organization_id
        or override.proposal_id != proposal.proposal_id
        or override.proposal_version != proposal.version
    ):
        raise DispatcherManualOverrideRevalidationError(
            "manual override, proposal, and snapshot scope do not match"
        )
    if (
        snapshot.snapshot_id != proposal.input_snapshot_id
        or snapshot.fingerprint != proposal.input_fingerprint
        or snapshot.period_start != proposal.period_start
        or snapshot.period_end != proposal.period_end
        or snapshot.operational_unit.external_identifier
        != proposal.operational_unit.external_identifier
    ):
        raise DispatcherManualOverrideRevalidationError(
            "snapshot is not the authoritative input for the proposal"
        )


def _validate_replacement_scope(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    replacement: ProposedShiftAssignment,
) -> None:
    if replacement.organization_id != snapshot.organization_id:
        raise DispatcherManualOverrideRevalidationError(
            "replacement assignment organization does not match snapshot"
        )
    if not snapshot.period_start <= replacement.date <= snapshot.period_end:
        raise DispatcherManualOverrideRevalidationError(
            "replacement assignment date falls outside snapshot period"
        )
    if (
        replacement.operational_unit.external_identifier
        != snapshot.operational_unit.external_identifier
    ):
        raise DispatcherManualOverrideRevalidationError(
            "replacement assignment operational unit does not match snapshot"
        )


def _resolve_demand(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    demand_trace_id: str,
) -> OperationalDemand:
    matches = tuple(
        demand
        for demand in snapshot.demands
        if compute_operational_demand_trace_id(demand) == demand_trace_id
    )
    if len(matches) != 1:
        raise DispatcherManualOverrideDemandNotFoundError(
            "replacement demand trace must resolve to exactly one snapshot demand"
        )
    return matches[0]


def _resolve_candidate(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    workforce_member_id: str,
) -> WorkforceCandidateSnapshot:
    matches = tuple(
        candidate
        for candidate in snapshot.workforce_candidates
        if candidate.workforce_member_id == workforce_member_id
    )
    if len(matches) != 1:
        raise DispatcherManualOverrideCandidateNotFoundError(
            "replacement workforce member must resolve to exactly one snapshot candidate"
        )
    return matches[0]


def _rebuilt_override(
    *,
    override: DispatcherManualOverride,
    violations: tuple[ConstraintEvaluation, ...],
) -> DispatcherManualOverride:
    return DispatcherManualOverride.model_validate(
        {
            **override.model_dump(),
            "violations": violations,
        }
    )


def revalidate_dispatcher_manual_override(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    previous: ComposedWeeklyWorkforceProposal,
    override: DispatcherManualOverride,
    replacement_assignment: ProposedShiftAssignment | None,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
) -> DispatcherManualOverride:
    _validate_authoritative_scope(
        snapshot=snapshot,
        previous=previous,
        override=override,
    )
    if override.operation_type == DispatcherOverrideOperationType.REMOVE_ASSIGNMENT:
        if replacement_assignment is not None:
            raise DispatcherManualOverrideRevalidationError(
                "REMOVE_ASSIGNMENT cannot include replacement assignment"
            )
        return _rebuilt_override(override=override, violations=())

    if replacement_assignment is None:
        raise DispatcherManualOverrideRevalidationError(
            f"{override.operation_type.value} requires replacement assignment"
        )
    _validate_replacement_scope(
        snapshot=snapshot,
        replacement=replacement_assignment,
    )
    demand = _resolve_demand(
        snapshot=snapshot,
        demand_trace_id=replacement_assignment.demand_trace_id,
    )
    candidate = _resolve_candidate(
        snapshot=snapshot,
        workforce_member_id=replacement_assignment.workforce_member_id,
    )
    decision = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
        capability_mappings=capability_mappings,
    )
    violations = tuple(
        evaluation for evaluation in decision.evaluations if not evaluation.passed
    )
    return _rebuilt_override(override=override, violations=violations)

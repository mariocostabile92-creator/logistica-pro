from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.workforce_auto_planning.coverage_gap import CoverageGap
from app.domain.workforce_auto_planning.dispatcher_manual_override import (
    DispatcherManualOverride,
    DispatcherOverrideOperationType,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)


class DispatcherWeeklyEditError(ValueError):
    pass


class DispatcherWeeklyEditAssignmentNotFoundError(DispatcherWeeklyEditError):
    pass


class DispatcherWeeklyEditScopeMismatchError(DispatcherWeeklyEditError):
    pass


class DispatcherWeeklyEditCommandMismatchError(DispatcherWeeklyEditError):
    pass


class DispatcherWeeklyEditUnknownDemandTraceError(DispatcherWeeklyEditError):
    pass


class DispatcherWeeklyEditCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    override: DispatcherManualOverride
    replacement_assignment: ProposedShiftAssignment | None = None
    created_at: datetime


def _validate_override_scope(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    override: DispatcherManualOverride,
) -> None:
    proposal = previous.proposal
    if (
        override.organization_id != proposal.organization_id
        or override.proposal_id != proposal.proposal_id
    ):
        raise DispatcherWeeklyEditScopeMismatchError(
            "manual override does not belong to proposal scope"
        )
    if override.proposal_version != proposal.version:
        raise DispatcherWeeklyEditCommandMismatchError(
            "manual override proposal version is stale"
        )


def _target_assignment(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    override: DispatcherManualOverride,
) -> ProposedShiftAssignment | None:
    if override.operation_type == DispatcherOverrideOperationType.ADD_ASSIGNMENT:
        return None
    matches = tuple(
        assignment
        for assignment in previous.assignments
        if assignment.assignment_id == override.assignment_id
    )
    if not matches:
        raise DispatcherWeeklyEditAssignmentNotFoundError(
            "target assignment was not found"
        )
    if len(matches) != 1:
        raise DispatcherWeeklyEditCommandMismatchError(
            "target assignment identity is ambiguous"
        )
    return matches[0]


def _validate_replacement_scope(
    *,
    proposal: WeeklyWorkforceProposal,
    replacement: ProposedShiftAssignment,
    known_demand_traces: frozenset[str],
) -> None:
    if replacement.organization_id != proposal.organization_id:
        raise DispatcherWeeklyEditScopeMismatchError(
            "replacement assignment organization does not match proposal"
        )
    if not proposal.period_start <= replacement.date <= proposal.period_end:
        raise DispatcherWeeklyEditScopeMismatchError(
            "replacement assignment date falls outside proposal period"
        )
    if (
        replacement.operational_unit.external_identifier
        != proposal.operational_unit.external_identifier
    ):
        raise DispatcherWeeklyEditScopeMismatchError(
            "replacement assignment operational unit does not match proposal"
        )
    if replacement.demand_trace_id not in known_demand_traces:
        raise DispatcherWeeklyEditUnknownDemandTraceError(
            "replacement assignment demand trace is not represented by proposal"
        )
    if replacement.origin != ProposedShiftAssignmentOrigin.MANUAL:
        raise DispatcherWeeklyEditCommandMismatchError(
            "replacement assignment origin must be MANUAL"
        )
    if replacement.status != ProposedShiftAssignmentStatus.PROPOSED:
        raise DispatcherWeeklyEditCommandMismatchError(
            "replacement assignment status must be PROPOSED"
        )


def _validate_operation(
    *,
    operation: DispatcherOverrideOperationType,
    target: ProposedShiftAssignment | None,
    replacement: ProposedShiftAssignment | None,
) -> None:
    if operation == DispatcherOverrideOperationType.REMOVE_ASSIGNMENT:
        if replacement is not None:
            raise DispatcherWeeklyEditCommandMismatchError(
                "REMOVE_ASSIGNMENT cannot include replacement assignment"
            )
        return
    if replacement is None:
        raise DispatcherWeeklyEditCommandMismatchError(
            f"{operation.value} requires replacement assignment"
        )
    if operation == DispatcherOverrideOperationType.MOVE_ASSIGNMENT:
        if target is None:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MOVE_ASSIGNMENT requires target assignment"
            )
        if replacement.assignment_id != target.assignment_id:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MOVE_ASSIGNMENT must preserve assignment_id"
            )
        if replacement.workforce_member_id != target.workforce_member_id:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MOVE_ASSIGNMENT must preserve workforce_member_id"
            )
    if operation == DispatcherOverrideOperationType.MODIFY_ASSIGNMENT:
        if target is None:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MODIFY_ASSIGNMENT requires target assignment"
            )
        if replacement.assignment_id != target.assignment_id:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MODIFY_ASSIGNMENT must preserve assignment_id"
            )
        if replacement.workforce_member_id != target.workforce_member_id:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MODIFY_ASSIGNMENT must preserve workforce_member_id"
            )
        if replacement.date != target.date:
            raise DispatcherWeeklyEditCommandMismatchError(
                "MODIFY_ASSIGNMENT must preserve operational date"
            )


def _apply_assignment_operation(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    operation: DispatcherOverrideOperationType,
    target: ProposedShiftAssignment | None,
    replacement: ProposedShiftAssignment | None,
) -> tuple[ProposedShiftAssignment, ...]:
    if operation == DispatcherOverrideOperationType.ADD_ASSIGNMENT:
        values = (*previous.assignments, replacement)
    elif operation == DispatcherOverrideOperationType.REMOVE_ASSIGNMENT:
        values = tuple(item for item in previous.assignments if item is not target)
    else:
        values = tuple(
            replacement if item is target else item for item in previous.assignments
        )
    if any(item is None for item in values):
        raise DispatcherWeeklyEditCommandMismatchError(
            "assignment operation produced an empty replacement"
        )
    assignments = tuple(item for item in values if item is not None)
    identifiers = [item.assignment_id for item in assignments]
    if len(identifiers) != len(set(identifiers)):
        raise DispatcherWeeklyEditCommandMismatchError(
            "assignment identity must be unique within proposal revision"
        )
    return tuple(
        sorted(
            assignments,
            key=lambda item: (
                item.date,
                item.time_window.external_identifier,
                item.workforce_member_id,
                item.assignment_id,
            ),
        )
    )


def _recalculate_coverage_gaps(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    assignments: tuple[ProposedShiftAssignment, ...],
) -> tuple[CoverageGap, ...]:
    proposed_by_trace: dict[str, int] = {}
    for assignment in assignments:
        proposed_by_trace[assignment.demand_trace_id] = (
            proposed_by_trace.get(assignment.demand_trace_id, 0) + 1
        )
    recalculated = tuple(
        CoverageGap.model_validate(
            {
                **gap.model_dump(),
                "proposed_quantity": proposed_by_trace.get(
                    gap.demand_trace_id, 0
                ),
                "gap_quantity": gap.required_quantity
                - proposed_by_trace.get(gap.demand_trace_id, 0),
            }
        )
        for gap in previous.coverage_gaps
    )
    return tuple(sorted(recalculated, key=lambda gap: gap.demand_trace_id))


def apply_dispatcher_weekly_edit(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    command: DispatcherWeeklyEditCommand,
) -> ComposedWeeklyWorkforceProposal:
    override = command.override
    _validate_override_scope(previous=previous, override=override)
    known_demand_traces = frozenset(
        gap.demand_trace_id for gap in previous.coverage_gaps
    )
    if len(known_demand_traces) != len(previous.coverage_gaps):
        raise DispatcherWeeklyEditCommandMismatchError(
            "proposal coverage gap demand traces must be unique"
        )
    target = _target_assignment(previous=previous, override=override)
    replacement = command.replacement_assignment
    _validate_operation(
        operation=override.operation_type,
        target=target,
        replacement=replacement,
    )
    if replacement is not None:
        _validate_replacement_scope(
            proposal=previous.proposal,
            replacement=replacement,
            known_demand_traces=known_demand_traces,
        )
    assignments = _apply_assignment_operation(
        previous=previous,
        operation=override.operation_type,
        target=target,
        replacement=replacement,
    )
    proposal = previous.proposal
    next_proposal = WeeklyWorkforceProposal(
        proposal_id=proposal.proposal_id,
        organization_id=proposal.organization_id,
        period_start=proposal.period_start,
        period_end=proposal.period_end,
        operational_unit=proposal.operational_unit,
        version=proposal.version + 1,
        input_snapshot_id=proposal.input_snapshot_id,
        input_fingerprint=proposal.input_fingerprint,
        policy_set_identifier=proposal.policy_set_identifier,
        policy_set_version=proposal.policy_set_version,
        status=WeeklyWorkforceProposalStatus.GENERATED,
        created_at=command.created_at,
    )
    return ComposedWeeklyWorkforceProposal(
        proposal=next_proposal,
        assignments=assignments,
        coverage_gaps=_recalculate_coverage_gaps(
            previous=previous,
            assignments=assignments,
        ),
        eligibility_decisions=previous.eligibility_decisions,
        preference_sets=previous.preference_sets,
        ranked_candidates=previous.ranked_candidates,
    )

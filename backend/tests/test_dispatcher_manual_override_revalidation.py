from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource

import pytest

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ComposedWeeklyWorkforceProposal,
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    CurrentMemberContractStateSnapshot,
    DispatcherManualOverride,
    DispatcherManualOverrideCandidateNotFoundError,
    DispatcherManualOverrideDemandNotFoundError,
    DispatcherManualOverrideRevalidationError,
    DispatcherOverrideOperationType,
    OperationalDemand,
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compute_operational_demand_trace_id,
    revalidate_dispatcher_manual_override,
)
from app.domain.workforce_auto_planning import (
    dispatcher_manual_override_revalidation as revalidation_module,
)


ORGANIZATION_ID = "organization-one"
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
OPERATIONAL_DATE = date(2026, 8, 24)
PERIOD_END = date(2026, 8, 30)
CREATED_AT = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY = "opaque-capability"
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)


def _demand(*, source: str = "normalized-source") -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=OPERATIONAL_DATE,
        time_window=WINDOW,
        capability_or_workload=CAPABILITY,
        base_quantity=1,
        target_quantity=1,
        source=source,
        applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
    )


def _assigned_time(value: str = "0") -> AssignedTimeSnapshot:
    return AssignedTimeSnapshot(
        status=AssignedTimeStatus.KNOWN,
        value=Decimal(value),
        unit=AssignedTimeUnit.MINUTES,
    )


def _approved_assignment() -> ApprovedAssignmentSnapshot:
    return ApprovedAssignmentSnapshot(
        assignment_reference="approved-conflict",
        date=OPERATIONAL_DATE,
        operational_unit=UNIT,
        shift_identifier="known-shift",
        time_window=TimeWindow(
            external_identifier="approved-window",
            starts_at="09:00",
            ends_at="11:00",
        ),
        assigned_time=_assigned_time("120"),
    )


def _candidate(
    *,
    member_id: str = "member-one",
    callable_value: bool = True,
    capabilities: tuple[str, ...] = (CAPABILITY,),
    contract_start: date | None = None,
    contract_end: date | None = None,
    weekly_hours: Decimal | None = Decimal("40"),
    assignments: tuple[ApprovedAssignmentSnapshot, ...] = (),
) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=member_id,
            display_name="Candidate one",
            capabilities=capabilities,
        ),
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=OPERATIONAL_DATE,
                availability=ResourceAvailability(
                    resource_identifier=member_id,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=callable_value,
                    observed_state=(
                        "available" if callable_value else "unavailable"
                    ),
                ),
            ),
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            contract_start=contract_start,
            contract_end=contract_end,
            weekly_hours=weekly_hours,
        ),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_approved_assignments=assignments,
        already_assigned_minutes_or_hours=_assigned_time(),
    )


def _snapshot(
    *,
    demands: tuple[OperationalDemand, ...] | None = None,
    candidates: tuple[WorkforceCandidateSnapshot, ...] | None = None,
) -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-one",
        organization_id=ORGANIZATION_ID,
        period_start=OPERATIONAL_DATE,
        period_end=PERIOD_END,
        operational_unit=UNIT,
        demands=demands if demands is not None else (_demand(),),
        workforce_candidates=(
            candidates if candidates is not None else (_candidate(),)
        ),
        policy_set_identifier="policy-set",
        policy_set_version="1",
        created_at=CREATED_AT,
        fingerprint="fingerprint-one",
    )


def _previous() -> ComposedWeeklyWorkforceProposal:
    return ComposedWeeklyWorkforceProposal(
        proposal=WeeklyWorkforceProposal(
            proposal_id="proposal-one",
            organization_id=ORGANIZATION_ID,
            period_start=OPERATIONAL_DATE,
            period_end=PERIOD_END,
            operational_unit=UNIT,
            version=1,
            input_snapshot_id="snapshot-one",
            input_fingerprint="fingerprint-one",
            policy_set_identifier="policy-set",
            policy_set_version="1",
            status=WeeklyWorkforceProposalStatus.GENERATED,
            created_at=CREATED_AT,
        ),
        assignments=(),
        coverage_gaps=(),
        eligibility_decisions=(),
        preference_sets=(),
        ranked_candidates=(),
    )


def _caller_violation() -> ConstraintEvaluation:
    return ConstraintEvaluation(
        code="caller-provided-violation",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=False,
        message="Caller-provided values are not authoritative.",
        rule_origin="caller",
    )


def _override(
    operation: DispatcherOverrideOperationType = (
        DispatcherOverrideOperationType.ADD_ASSIGNMENT
    ),
    *,
    violations: tuple[ConstraintEvaluation, ...] = (),
) -> DispatcherManualOverride:
    return DispatcherManualOverride(
        override_id="override-one",
        organization_id=ORGANIZATION_ID,
        proposal_id="proposal-one",
        proposal_version=1,
        assignment_id=(
            None
            if operation == DispatcherOverrideOperationType.ADD_ASSIGNMENT
            else "assignment-target"
        ),
        operation_type=operation,
        reason="Dispatcher decision.",
        actor_id="dispatcher-one",
        violations=violations,
        created_at=CREATED_AT,
    )


def _replacement(
    *,
    demand: OperationalDemand | None = None,
    member_id: str = "member-one",
) -> ProposedShiftAssignment:
    resolved_demand = demand if demand is not None else _demand()
    return ProposedShiftAssignment(
        assignment_id="assignment-replacement",
        demand_trace_id=compute_operational_demand_trace_id(resolved_demand),
        organization_id=ORGANIZATION_ID,
        workforce_member_id=member_id,
        date=resolved_demand.date,
        operational_unit=resolved_demand.operational_unit,
        shift_identifier=None,
        time_window=resolved_demand.time_window,
        capability_or_workload=resolved_demand.capability_or_workload,
        origin=ProposedShiftAssignmentOrigin.MANUAL,
        status=ProposedShiftAssignmentStatus.PROPOSED,
        deterministic_priority=0,
        reasons=(
            ProposedAssignmentReason(
                code="manual-decision",
                message="Dispatcher selected this assignment.",
            ),
        ),
        locked=False,
    )


def _revalidate(
    *,
    snapshot: WeeklyPlanningInputSnapshot | None = None,
    override: DispatcherManualOverride | None = None,
    replacement: ProposedShiftAssignment | None = None,
    mappings: tuple[WorkloadCapabilityMapping, ...] = MAPPINGS,
) -> DispatcherManualOverride:
    selected_override = override if override is not None else _override()
    selected_replacement = (
        replacement
        if replacement is not None
        else (
            None
            if selected_override.operation_type
            == DispatcherOverrideOperationType.REMOVE_ASSIGNMENT
            else _replacement()
        )
    )
    return revalidate_dispatcher_manual_override(
        snapshot=snapshot if snapshot is not None else _snapshot(),
        previous=_previous(),
        override=selected_override,
        replacement_assignment=selected_replacement,
        capability_mappings=mappings,
    )


def _violation_codes(result: DispatcherManualOverride) -> list[str]:
    return [item.code for item in result.violations]


def test_add_valid_assignment_has_no_violations() -> None:
    result = _revalidate()

    assert result.violations == ()


@pytest.mark.parametrize(
    ("candidate", "mappings", "expected_code"),
    (
        (_candidate(callable_value=False), MAPPINGS, "daily-callability"),
        (
            _candidate(weekly_hours=Decimal("1")),
            MAPPINGS,
            "weekly-hours-capacity",
        ),
        (
            _candidate(capabilities=("other-capability",)),
            MAPPINGS,
            "capability-compatibility",
        ),
        (
            _candidate(contract_start=date(2026, 8, 25)),
            MAPPINGS,
            "contract-date-validity",
        ),
        (
            _candidate(assignments=(_approved_assignment(),)),
            MAPPINGS,
            "approved-assignment-conflict",
        ),
    ),
)
def test_add_preserves_authoritative_business_failure_as_violation(
    candidate: WorkforceCandidateSnapshot,
    mappings: tuple[WorkloadCapabilityMapping, ...],
    expected_code: str,
) -> None:
    result = _revalidate(
        snapshot=_snapshot(candidates=(candidate,)),
        mappings=mappings,
    )

    assert _violation_codes(result) == [expected_code]


def test_multiple_failures_preserve_evaluator_order() -> None:
    candidate = _candidate(
        callable_value=False,
        capabilities=("other-capability",),
        contract_start=date(2026, 8, 25),
        weekly_hours=Decimal("1"),
        assignments=(_approved_assignment(),),
    )

    result = _revalidate(snapshot=_snapshot(candidates=(candidate,)))

    assert _violation_codes(result) == [
        "daily-callability",
        "approved-assignment-conflict",
        "capability-compatibility",
        "contract-date-validity",
        "weekly-hours-capacity",
    ]
    assert all(not item.passed for item in result.violations)


def test_caller_violations_are_replaced_and_passed_constraints_are_excluded() -> None:
    result = _revalidate(override=_override(violations=(_caller_violation(),)))

    assert result.violations == ()


def test_remove_clears_caller_violations_without_revalidation() -> None:
    override = _override(
        DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
        violations=(_caller_violation(),),
    )

    result = _revalidate(override=override)

    assert result.violations == ()


@pytest.mark.parametrize(
    "operation",
    (
        DispatcherOverrideOperationType.REPLACE_ASSIGNMENT,
        DispatcherOverrideOperationType.MOVE_ASSIGNMENT,
        DispatcherOverrideOperationType.MODIFY_ASSIGNMENT,
    ),
)
def test_replacement_operations_revalidate_replacement_driver(
    operation: DispatcherOverrideOperationType,
) -> None:
    valid = _candidate(member_id="member-valid")
    blocked = _candidate(member_id="member-blocked", callable_value=False)
    snapshot = _snapshot(candidates=(valid, blocked))

    result = _revalidate(
        snapshot=snapshot,
        override=_override(operation),
        replacement=_replacement(member_id="member-blocked"),
    )

    assert _violation_codes(result) == ["daily-callability"]


def test_unknown_demand_trace_is_structural_error() -> None:
    replacement = _replacement().model_copy(
        update={"demand_trace_id": "unknown-demand-trace"}
    )

    with pytest.raises(DispatcherManualOverrideDemandNotFoundError):
        _revalidate(replacement=replacement)


def test_unknown_candidate_is_structural_error() -> None:
    with pytest.raises(DispatcherManualOverrideCandidateNotFoundError):
        _revalidate(replacement=_replacement(member_id="unknown-member"))


def test_ambiguous_candidate_is_structural_error() -> None:
    duplicated = (_candidate(), _candidate())

    with pytest.raises(DispatcherManualOverrideCandidateNotFoundError):
        _revalidate(snapshot=_snapshot(candidates=duplicated))


def test_source_differentiates_demand_resolution_by_trace(monkeypatch) -> None:
    first = _demand(source="source-one")
    second = _demand(source="source-two")
    observed_sources: list[str] = []
    actual_evaluator = revalidation_module.evaluate_workforce_candidate_eligibility

    def recording_evaluator(**values):
        observed_sources.append(values["demand"].source)
        return actual_evaluator(**values)

    monkeypatch.setattr(
        revalidation_module,
        "evaluate_workforce_candidate_eligibility",
        recording_evaluator,
    )

    _revalidate(
        snapshot=_snapshot(demands=(first, second)),
        replacement=_replacement(demand=second),
    )

    assert observed_sources == ["source-two"]


def test_business_failure_does_not_invalidate_override() -> None:
    original = _override()

    result = _revalidate(
        snapshot=_snapshot(candidates=(_candidate(callable_value=False),)),
        override=original,
    )

    assert isinstance(result, DispatcherManualOverride)
    assert result.override_id == original.override_id
    assert _violation_codes(result) == ["daily-callability"]


def test_inputs_are_not_mutated_and_result_is_a_new_override() -> None:
    snapshot = _snapshot(candidates=(_candidate(callable_value=False),))
    override = _override(violations=(_caller_violation(),))
    replacement = _replacement()
    before_snapshot = snapshot.model_dump(mode="json")
    before_override = override.model_dump(mode="json")
    before_replacement = replacement.model_dump(mode="json")

    result = _revalidate(
        snapshot=snapshot,
        override=override,
        replacement=replacement,
    )

    assert result is not override
    assert snapshot.model_dump(mode="json") == before_snapshot
    assert override.model_dump(mode="json") == before_override
    assert replacement.model_dump(mode="json") == before_replacement


def test_revalidation_rejects_replacement_outside_snapshot_scope() -> None:
    replacement = _replacement().model_copy(
        update={"organization_id": "organization-two"}
    )

    with pytest.raises(DispatcherManualOverrideRevalidationError):
        _revalidate(replacement=replacement)


def test_revalidation_delegates_eligibility_without_query_or_persistence() -> None:
    source = getsource(revalidation_module)

    assert source.count("evaluate_workforce_candidate_eligibility(") == 1
    assert "daily-callability" not in source
    assert "weekly-hours-capacity" not in source
    assert "repository" not in source.casefold()
    assert "sqlalchemy" not in source.casefold()
    assert "fastapi" not in source.casefold()

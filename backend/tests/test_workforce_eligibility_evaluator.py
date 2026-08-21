from datetime import date
from decimal import Decimal
import inspect
from pathlib import Path

import pytest

from app.domain.workforce_auto_planning import (
    workforce_eligibility_evaluator as evaluator_module,
)
from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AmbiguousCapabilityMappingError,
    AppliedPolicyMetadata,
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    evaluate_workforce_candidate_eligibility,
)


OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-north", name="North Hub")
OTHER_UNIT = OperationalUnit(external_identifier="unit-south")
WINDOW = TimeWindow(
    external_identifier="morning-window",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY_MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier="generic-delivery-capability",
        required_capabilities=("uninterpreted-capability",),
    ),
)


def _demand(*, organization_id: str = "organization-one") -> OperationalDemand:
    return OperationalDemand(
        organization_id=organization_id,
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=WINDOW,
        capability_or_workload="generic-delivery-capability",
        base_quantity=10,
        target_quantity=10,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="baseline-policy"),
    )


def _unit_scope(
    status: CandidateOperationalUnitScopeStatus,
) -> CandidateOperationalUnitScope:
    return CandidateOperationalUnitScope(
        status=status,
        requested_unit=UNIT,
        candidate_unit=(
            None
            if status == CandidateOperationalUnitScopeStatus.UNKNOWN
            else (
                UNIT
                if status == CandidateOperationalUnitScopeStatus.MATCHED
                else OTHER_UNIT
            )
        ),
    )


def _candidate(
    *,
    organization_id: str = "organization-one",
    unit_status: CandidateOperationalUnitScopeStatus = (
        CandidateOperationalUnitScopeStatus.MATCHED
    ),
    callable_value: bool = True,
    observed_state: str | None = "available",
    include_readiness: bool = True,
    assignments: tuple[ApprovedAssignmentSnapshot, ...] = (),
    capabilities: tuple[str, ...] = ("uninterpreted-capability",),
    contract_start: date | None = None,
    contract_end: date | None = None,
) -> WorkforceCandidateSnapshot:
    availability = (
        (
            WorkforceCandidateAvailabilitySnapshot(
                date=OPERATION_DATE,
                availability=ResourceAvailability(
                    resource_identifier="opaque-member-42",
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=callable_value,
                    observed_state=observed_state,
                    reason="Authoritative Workforce readiness reason.",
                    origin="workforce-readiness",
                ),
            ),
        )
        if include_readiness
        else ()
    )
    return WorkforceCandidateSnapshot(
        organization_id=organization_id,
        human_resource=HumanResource(
            external_identifier="opaque-member-42",
            display_name="Driver Example",
            capabilities=capabilities,
        ),
        availability=availability,
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            employment_type="uninterpreted-contract",
            contract_start=contract_start,
            contract_end=contract_end,
            weekly_hours=Decimal("40"),
            is_reserve=False,
        ),
        operational_unit_scope=_unit_scope(unit_status),
        recent_consecutivity=99,
        already_approved_assignments=assignments,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("0"),
            unit=AssignedTimeUnit.MINUTES,
        ),
        evidence=(
            ConstraintEvidence(
                key=(
                    "workforce-readiness:2026-08-24:limitation:1"
                ),
                value="Preserved limitation.",
            ),
        ),
    )


def _assignment(
    reference: str,
    *,
    operation_date: date = OPERATION_DATE,
    start: str | None = "12:00",
    end: str | None = "16:00",
) -> ApprovedAssignmentSnapshot:
    assigned_time = (
        AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("240"),
            unit=AssignedTimeUnit.MINUTES,
        )
        if start is not None and end is not None
        else AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN)
    )
    return ApprovedAssignmentSnapshot(
        assignment_reference=reference,
        date=operation_date,
        operational_unit=UNIT,
        shift_identifier="generic-shift",
        time_window=TimeWindow(
            external_identifier=f"{reference}-window",
            starts_at=start,
            ends_at=end,
        ),
        assigned_time=assigned_time,
    )


def _evaluate(
    *,
    capability_mappings: tuple[
        WorkloadCapabilityMapping, ...
    ] = CAPABILITY_MAPPINGS,
    **candidate_updates,
):
    return evaluate_workforce_candidate_eligibility(
        candidate=_candidate(**candidate_updates),
        demand=_demand(),
        capability_mappings=capability_mappings,
    )


def _evaluation(decision, code: str) -> ConstraintEvaluation:
    return next(item for item in decision.evaluations if item.code == code)


def test_all_six_hard_constraints_pass():
    candidate = _candidate()
    demand = _demand()

    decision = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
        capability_mappings=CAPABILITY_MAPPINGS,
    )

    assert decision.eligible is True
    assert len(decision.evaluations) == 6
    assert all(item.passed for item in decision.evaluations)
    assert decision.exclusion_reasons == ()
    assert decision.warnings == ()
    assert decision.organization_id == demand.organization_id
    assert decision.workforce_member_id == candidate.workforce_member_id
    assert decision.operational_date == demand.date
    assert decision.operational_unit == demand.operational_unit
    assert decision.time_window == demand.time_window
    assert (
        decision.capability_or_workload
        == demand.capability_or_workload
    )


def test_organization_mismatch_is_a_normal_non_eligible_decision():
    decision = _evaluate(organization_id="organization-two")

    assert decision.eligible is False
    assert _evaluation(decision, "organization-match").passed is False
    assert [item.code for item in decision.exclusion_reasons] == [
        "organization-match"
    ]


def test_mismatched_operational_unit_is_not_eligible():
    decision = _evaluate(
        unit_status=CandidateOperationalUnitScopeStatus.MISMATCHED
    )

    assert decision.eligible is False
    assert _evaluation(decision, "operational-unit-match").passed is False


def test_unknown_operational_unit_fails_closed():
    decision = _evaluate(
        unit_status=CandidateOperationalUnitScopeStatus.UNKNOWN
    )

    assert decision.eligible is False
    unit_evaluation = _evaluation(decision, "operational-unit-match")
    assert unit_evaluation.passed is False
    assert "unknown" in unit_evaluation.message.casefold()


def test_non_callable_readiness_is_not_eligible_and_preserves_evidence():
    decision = _evaluate(callable_value=False, observed_state="rest")

    assert decision.eligible is False
    callability = _evaluation(decision, "daily-callability")
    assert callability.passed is False
    evidence = {item.key: item.value for item in callability.evidence}
    assert evidence["readiness-reason"] == (
        "Authoritative Workforce readiness reason."
    )
    assert evidence["readiness-limitation-1"] == "Preserved limitation."
    assert evidence["observed-state"] == "rest"


def test_unknown_availability_status_fails_closed():
    decision = _evaluate(callable_value=True, observed_state="unknown")

    assert decision.eligible is False
    callability = _evaluation(decision, "daily-callability")
    assert callability.passed is False
    assert "unknown" in callability.message.casefold()


def test_missing_daily_readiness_fails_closed():
    decision = _evaluate(include_readiness=False)

    assert decision.eligible is False
    callability = _evaluation(decision, "daily-callability")
    assert callability.passed is False
    evidence = {item.key: item.value for item in callability.evidence}
    assert evidence["readiness-present"] is False


def test_no_approved_assignment_makes_fourth_constraint_pass():
    decision = _evaluate(assignments=())
    conflict = _evaluation(decision, "approved-assignment-conflict")

    assert conflict.passed is True
    assert conflict.message == "Candidate has no approved assignments."
    assert "approved-assignment-conflict" not in {
        item.code for item in decision.exclusion_reasons
    }


def test_approved_assignment_on_another_date_passes():
    decision = _evaluate(
        assignments=(
            _assignment(
                "other-date",
                operation_date=date(2026, 8, 23),
                start="08:00",
                end="12:00",
            ),
        )
    )

    assert _evaluation(
        decision, "approved-assignment-conflict"
    ).passed is True


def test_non_overlapping_approved_assignment_passes():
    decision = _evaluate(
        assignments=(_assignment("no-overlap", start="12:00", end="16:00"),)
    )

    assert _evaluation(
        decision, "approved-assignment-conflict"
    ).passed is True


def test_confirmed_overlap_fails_with_one_exclusion_reason():
    decision = _evaluate(
        assignments=(_assignment("overlap", start="10:00", end="14:00"),)
    )
    conflict = _evaluation(decision, "approved-assignment-conflict")

    assert decision.eligible is False
    assert conflict.passed is False
    assert "confirmed time conflict" in conflict.message
    assert [
        item.code
        for item in decision.exclusion_reasons
        if item.code == "approved-assignment-conflict"
    ] == ["approved-assignment-conflict"]


def test_unknown_conflict_status_fails_closed():
    decision = _evaluate(
        assignments=(_assignment("unknown", start=None, end=None),)
    )
    conflict = _evaluation(decision, "approved-assignment-conflict")
    evidence = {item.key: item.value for item in conflict.evidence}

    assert decision.eligible is False
    assert conflict.passed is False
    assert "cannot be determined" in conflict.message
    assert evidence["aggregate-conflict-status"] == "UNKNOWN"


def test_confirmed_conflict_takes_precedence_over_unknown():
    decision = _evaluate(
        assignments=(
            _assignment("unknown", start=None, end=None),
            _assignment("conflict", start="10:00", end="14:00"),
        )
    )
    conflict = _evaluation(decision, "approved-assignment-conflict")
    evidence = {item.key: item.value for item in conflict.evidence}

    assert conflict.passed is False
    assert evidence["aggregate-conflict-status"] == "CONFLICT"
    assert "confirmed time conflict" in conflict.message
    assert {value for key, value in evidence.items() if key.endswith(":status")} == {
        "CONFLICT",
        "UNKNOWN",
    }


def test_multiple_no_conflict_assignments_pass():
    decision = _evaluate(
        assignments=(
            _assignment("later", start="12:00", end="16:00"),
            _assignment(
                "other-date",
                operation_date=date(2026, 8, 23),
                start="08:00",
                end="12:00",
            ),
        )
    )

    assert decision.eligible is True
    assert _evaluation(
        decision, "approved-assignment-conflict"
    ).passed is True


def test_callability_and_conflict_failures_produce_two_exclusion_reasons():
    decision = _evaluate(
        callable_value=False,
        observed_state="rest",
        assignments=(_assignment("conflict", start="10:00", end="14:00"),),
    )

    assert [item.code for item in decision.exclusion_reasons] == [
        "daily-callability",
        "approved-assignment-conflict",
    ]


def test_compatible_capability_makes_fifth_constraint_pass():
    decision = _evaluate()
    capability = _evaluation(decision, "capability-compatibility")

    assert capability.passed is True
    assert "capability-compatibility" not in {
        item.code for item in decision.exclusion_reasons
    }


def test_incompatible_capability_fails_with_one_exclusion_reason():
    decision = _evaluate(
        capability_mappings=(
            WorkloadCapabilityMapping(
                workload_identifier="generic-delivery-capability",
                required_capabilities=("different-capability",),
            ),
        )
    )
    capability = _evaluation(decision, "capability-compatibility")
    evidence = {item.key: item.value for item in capability.evidence}

    assert decision.eligible is False
    assert capability.passed is False
    assert evidence["capability-compatibility-status"] == "INCOMPATIBLE"
    assert [
        item.code
        for item in decision.exclusion_reasons
        if item.code == "capability-compatibility"
    ] == ["capability-compatibility"]


def test_unknown_capability_mapping_fails_closed():
    decision = _evaluate(capability_mappings=())
    capability = _evaluation(decision, "capability-compatibility")
    evidence = {item.key: item.value for item in capability.evidence}

    assert decision.eligible is False
    assert capability.passed is False
    assert evidence["capability-compatibility-status"] == "UNKNOWN"
    assert capability.message == (
        "No authoritative capability mapping is available."
    )


def test_empty_candidate_capabilities_with_mapping_fail():
    decision = _evaluate(capabilities=())

    assert decision.eligible is False
    assert _evaluation(
        decision, "capability-compatibility"
    ).passed is False


def test_ambiguous_capability_mapping_error_propagates():
    mappings = (
        *CAPABILITY_MAPPINGS,
        WorkloadCapabilityMapping(
            workload_identifier="generic-delivery-capability",
            required_capabilities=("another-capability",),
        ),
    )

    with pytest.raises(AmbiguousCapabilityMappingError):
        _evaluate(capability_mappings=mappings)


def test_contract_date_without_limits_makes_sixth_constraint_pass():
    decision = _evaluate()
    contract_date = _evaluation(decision, "contract-date-validity")
    evidence = {item.key: item.value for item in contract_date.evidence}

    assert contract_date.passed is True
    assert evidence["contract-date-eligibility-status"] == "ELIGIBLE"
    assert evidence["contract-date-eligibility-reason-code"] == (
        "no-contract-date-limits"
    )
    assert "contract-date-validity" not in {
        item.code for item in decision.exclusion_reasons
    }


def test_date_before_contract_start_fails_with_one_exclusion_reason():
    decision = _evaluate(contract_start=date(2026, 8, 25))
    contract_date = _evaluation(decision, "contract-date-validity")

    assert decision.eligible is False
    assert contract_date.passed is False
    assert [
        item.code
        for item in decision.exclusion_reasons
        if item.code == "contract-date-validity"
    ] == ["contract-date-validity"]


def test_date_after_contract_end_fails_with_one_exclusion_reason():
    decision = _evaluate(contract_end=date(2026, 8, 23))
    contract_date = _evaluation(decision, "contract-date-validity")
    evidence = {item.key: item.value for item in contract_date.evidence}

    assert decision.eligible is False
    assert contract_date.passed is False
    assert evidence["contract-date-eligibility-reason-code"] == (
        "after-contract-end"
    )
    assert [item.code for item in decision.exclusion_reasons] == [
        "contract-date-validity"
    ]


def test_contract_start_boundary_is_inclusive():
    decision = _evaluate(contract_start=OPERATION_DATE)

    assert decision.eligible is True
    assert _evaluation(decision, "contract-date-validity").passed is True


def test_contract_end_boundary_is_inclusive():
    decision = _evaluate(contract_end=OPERATION_DATE)

    assert decision.eligible is True
    assert _evaluation(decision, "contract-date-validity").passed is True


def test_contract_date_integration_does_not_change_first_five_constraints():
    eligible = _evaluate(
        contract_start=OPERATION_DATE,
        contract_end=OPERATION_DATE,
    )
    ineligible = _evaluate(contract_start=date(2026, 8, 25))

    assert eligible.evaluations[:5] == ineligible.evaluations[:5]
    assert all(item.passed for item in eligible.evaluations[:5])


def test_two_simultaneous_failures_produce_two_exclusion_reasons():
    decision = _evaluate(
        organization_id="organization-two",
        unit_status=CandidateOperationalUnitScopeStatus.UNKNOWN,
    )

    assert [item.code for item in decision.exclusion_reasons] == [
        "organization-match",
        "operational-unit-match",
    ]


def test_three_failures_produce_three_exclusion_reasons():
    decision = _evaluate(
        organization_id="organization-two",
        unit_status=CandidateOperationalUnitScopeStatus.UNKNOWN,
        include_readiness=False,
    )

    assert [item.code for item in decision.exclusion_reasons] == [
        "organization-match",
        "operational-unit-match",
        "daily-callability",
    ]


def test_evaluations_are_always_six_hard_constraints_in_stable_order():
    decision = _evaluate(include_readiness=False)

    assert [item.code for item in decision.evaluations] == [
        "organization-match",
        "operational-unit-match",
        "daily-callability",
        "approved-assignment-conflict",
        "capability-compatibility",
        "contract-date-validity",
    ]
    assert all(
        item.category == ConstraintEvaluationCategory.HARD_CONSTRAINT
        for item in decision.evaluations
    )
    assert all(item.rule_origin == "core-policy" for item in decision.evaluations)


def test_passed_evaluations_do_not_create_exclusion_reasons():
    decision = _evaluate(include_readiness=False)

    failed_codes = {
        item.code for item in decision.evaluations if not item.passed
    }
    assert {item.code for item in decision.exclusion_reasons} == failed_codes
    assert "organization-match" not in failed_codes
    assert "operational-unit-match" not in failed_codes


def test_same_input_is_deterministic_and_evaluator_has_no_side_effects():
    candidate = _candidate()
    demand = _demand()
    candidate_before = candidate.model_dump(mode="json")
    demand_before = demand.model_dump(mode="json")

    first = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
        capability_mappings=CAPABILITY_MAPPINGS,
    )
    second = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
        capability_mappings=CAPABILITY_MAPPINGS,
    )

    assert first == second
    assert candidate.model_dump(mode="json") == candidate_before
    assert demand.model_dump(mode="json") == demand_before


def test_evaluator_has_no_out_of_scope_rules_or_dependencies():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "workforce_eligibility_evaluator.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "candidate.capabilities",
        "recent_consecutivity",
        "plugins.workforce",
        "repository",
        "sqlalchemy",
        "fastapi",
        "time.fromisoformat",
        ".starts_at",
        ".ends_at",
        "weekly_hours",
        "employment_type",
        "is_reserve",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
    assert source.count("evaluate_approved_assignment_conflict(") == 1


def test_capability_integration_reuses_a4_without_new_matching_logic():
    source = inspect.getsource(
        evaluator_module._capability_compatibility_evaluation
    ).casefold()

    assert source.count("evaluate_capability_compatibility(") == 1
    forbidden_fragments = (
        "casefold",
        "startswith",
        "endswith",
        "substring",
        "weekly_hours",
        "contract_start",
        "contract_end",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


def test_contract_date_integration_reuses_a5a_without_new_contract_rules():
    source = inspect.getsource(
        evaluator_module._contract_date_validity_evaluation
    ).casefold()

    assert source.count("evaluate_contract_date_eligibility(") == 1
    forbidden_fragments = (
        "weekly_hours",
        "employment_type",
        "is_reserve",
        "contract_start",
        "contract_end",
        "part-time",
        "full-time",
        "ranking",
        "scoring",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

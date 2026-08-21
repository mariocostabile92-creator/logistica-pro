from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
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
            capabilities=("uninterpreted-capability",),
        ),
        availability=availability,
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            employment_type="uninterpreted-contract",
            weekly_hours=Decimal("40"),
            is_reserve=False,
        ),
        operational_unit_scope=_unit_scope(unit_status),
        recent_consecutivity=99,
        already_approved_assignments=(),
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


def _evaluate(**candidate_updates):
    return evaluate_workforce_candidate_eligibility(
        candidate=_candidate(**candidate_updates),
        demand=_demand(),
    )


def _evaluation(decision, code: str) -> ConstraintEvaluation:
    return next(item for item in decision.evaluations if item.code == code)


def test_all_three_hard_constraints_pass():
    candidate = _candidate()
    demand = _demand()

    decision = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
    )

    assert decision.eligible is True
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


def test_evaluations_are_always_three_hard_constraints_in_stable_order():
    decision = _evaluate(include_readiness=False)

    assert [item.code for item in decision.evaluations] == [
        "organization-match",
        "operational-unit-match",
        "daily-callability",
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
    )
    second = evaluate_workforce_candidate_eligibility(
        candidate=candidate,
        demand=demand,
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
        "already_approved_assignments",
        "applicable_contract_state",
        "plugins.workforce",
        "repository",
        "sqlalchemy",
        "fastapi",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

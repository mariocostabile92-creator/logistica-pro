from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import HumanResource, OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    PlanningPreferenceOutcome,
    WorkforceCandidateSnapshot,
    evaluate_existing_assignment_stability_preference,
)


OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one")
OTHER_UNIT = OperationalUnit(external_identifier="unit-two")


def _demand(
    *,
    starts_at: str | None = "08:00",
    ends_at: str | None = "12:00",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id="organization-one",
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=TimeWindow(
            external_identifier="demand-window",
            starts_at=starts_at,
            ends_at=ends_at,
        ),
        capability_or_workload="opaque-capability",
        base_quantity=1,
        target_quantity=1,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="policy-one"),
    )


def _assignment(
    reference: str = "assignment-one",
    *,
    operation_date: date = OPERATION_DATE,
    starts_at: str | None = "08:00",
    ends_at: str | None = "12:00",
    operational_unit: OperationalUnit | None = UNIT,
    shift_identifier: str | None = "opaque-shift-one",
) -> ApprovedAssignmentSnapshot:
    return ApprovedAssignmentSnapshot(
        assignment_reference=reference,
        date=operation_date,
        operational_unit=operational_unit,
        shift_identifier=shift_identifier,
        time_window=TimeWindow(
            external_identifier=f"{reference}-window",
            starts_at=starts_at,
            ends_at=ends_at,
        ),
        assigned_time=AssignedTimeSnapshot(
            status=AssignedTimeStatus.UNKNOWN
        ),
    )


def _candidate(
    assignments: tuple[ApprovedAssignmentSnapshot, ...],
) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id="organization-one",
        human_resource=HumanResource(external_identifier="candidate-one"),
        applicable_contract_state=CurrentMemberContractStateSnapshot(),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_approved_assignments=assignments,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("0"),
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _evaluate(
    *assignments: ApprovedAssignmentSnapshot,
    demand: OperationalDemand | None = None,
    priority: int = 5,
):
    return evaluate_existing_assignment_stability_preference(
        candidate=_candidate(assignments),
        demand=demand if demand is not None else _demand(),
        priority=priority,
    )


def test_exact_date_window_and_unit_match_is_preferred():
    result = _evaluate(_assignment())
    evidence = {item.key: item.value for item in result.evidence}

    assert result.outcome == PlanningPreferenceOutcome.PREFERRED
    assert result.code == "existing-assignment-stability"
    assert evidence["compatible-assignment-reference"] == "assignment-one"
    assert evidence["decision-reason"] == "compatible-assignment-found"


@pytest.mark.parametrize(
    "assignment",
    (
        _assignment(operation_date=date(2026, 8, 23)),
        _assignment(starts_at="09:00"),
        _assignment(ends_at="13:00"),
        _assignment(operational_unit=OTHER_UNIT),
        _assignment(operational_unit=None),
        _assignment(starts_at=None),
        _assignment(ends_at=None),
        _assignment(starts_at="12:00", ends_at="12:00"),
        _assignment(starts_at="13:00", ends_at="12:00"),
    ),
)
def test_non_authoritative_or_incompatible_assignment_is_neutral(assignment):
    result = _evaluate(assignment)

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert result.message == (
        "No approved assignment authoritatively matches the demand."
    )


def test_invalid_demand_window_is_neutral():
    result = _evaluate(
        _assignment(),
        demand=_demand(starts_at="12:00", ends_at="08:00"),
    )

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL


def test_no_assignment_is_neutral_without_penalty():
    result = _evaluate()
    evidence = {item.key: item.value for item in result.evidence}

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert evidence["evaluated-assignment-count"] == 0
    assert evidence["compatible-assignment-reference"] is None


def test_multiple_assignments_with_one_compatible_are_preferred_deterministically():
    incompatible = _assignment(
        "z-incompatible",
        operation_date=date(2026, 8, 23),
    )
    compatible = _assignment("a-compatible")

    first = _evaluate(incompatible, compatible)
    second = _evaluate(compatible, incompatible)

    assert first == second
    assert first.outcome == PlanningPreferenceOutcome.PREFERRED
    assert dict(
        (item.key, item.value) for item in first.evidence
    )["compatible-assignment-reference"] == "a-compatible"


def test_multiple_assignments_without_compatible_are_neutral():
    result = _evaluate(
        _assignment("wrong-date", operation_date=date(2026, 8, 23)),
        _assignment("wrong-unit", operational_unit=OTHER_UNIT),
    )

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL


def test_shift_identifier_does_not_influence_result():
    first = _evaluate(_assignment(shift_identifier="shift-one"))
    second = _evaluate(_assignment(shift_identifier="shift-two"))

    assert first == second
    assert first.outcome == PlanningPreferenceOutcome.PREFERRED


def test_priority_is_preserved_and_contract_validates_it():
    result = _evaluate(_assignment(), priority=8)

    assert result.priority == 8
    with pytest.raises(ValidationError):
        _evaluate(_assignment(), priority=True)


def test_output_and_evidence_are_immutable():
    result = _evaluate(_assignment())

    with pytest.raises(ValidationError):
        result.outcome = PlanningPreferenceOutcome.NEUTRAL
    with pytest.raises(TypeError):
        result.evidence[0] = result.evidence[0]


def test_module_never_deprioritizes_and_has_no_ranking_or_external_dependencies():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "existing_assignment_stability_preference.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "deprioritized",
        "shift_identifier",
        "capability_or_workload",
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "repository",
        "sqlalchemy",
        "fastapi",
        "score",
        "weighted",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

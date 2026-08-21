from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import HumanResource, OperationalUnit
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    CurrentMemberContractStateSnapshot,
    PlanningPreferenceOutcome,
    WorkforceCandidateSnapshot,
    evaluate_lower_weekly_load_preference,
)


UNIT = OperationalUnit(external_identifier="unit-one")


def _assigned(
    *,
    status: AssignedTimeStatus = AssignedTimeStatus.KNOWN,
    value: Decimal | None = Decimal("0"),
    unit: AssignedTimeUnit | None = AssignedTimeUnit.MINUTES,
) -> AssignedTimeSnapshot:
    return AssignedTimeSnapshot(status=status, value=value, unit=unit)


def _candidate(
    identifier: str,
    assigned_time: AssignedTimeSnapshot,
) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id="organization-one",
        human_resource=HumanResource(external_identifier=identifier),
        applicable_contract_state=CurrentMemberContractStateSnapshot(),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=assigned_time,
    )


def _evaluate(
    candidate_assigned: AssignedTimeSnapshot,
    compared_assigned: AssignedTimeSnapshot,
    *,
    priority: int = 3,
):
    return evaluate_lower_weekly_load_preference(
        candidate=_candidate("candidate-one", candidate_assigned),
        compared_candidate=_candidate("candidate-two", compared_assigned),
        priority=priority,
    )


@pytest.mark.parametrize(
    ("candidate_minutes", "compared_minutes", "expected"),
    (
        (Decimal("120"), Decimal("240"), PlanningPreferenceOutcome.PREFERRED),
        (
            Decimal("240"),
            Decimal("120"),
            PlanningPreferenceOutcome.DEPRIORITIZED,
        ),
        (Decimal("120"), Decimal("120"), PlanningPreferenceOutcome.NEUTRAL),
    ),
)
def test_known_minute_loads_produce_expected_outcome(
    candidate_minutes,
    compared_minutes,
    expected,
):
    result = _evaluate(
        _assigned(value=candidate_minutes),
        _assigned(value=compared_minutes),
    )

    assert result.outcome == expected
    assert result.code == "lower-weekly-load"


@pytest.mark.parametrize(
    ("candidate_hours", "compared_minutes", "expected"),
    (
        (Decimal("2"), Decimal("180"), PlanningPreferenceOutcome.PREFERRED),
        (
            Decimal("4"),
            Decimal("180"),
            PlanningPreferenceOutcome.DEPRIORITIZED,
        ),
    ),
)
def test_hours_are_converted_to_minutes_without_rounding(
    candidate_hours,
    compared_minutes,
    expected,
):
    result = _evaluate(
        _assigned(value=candidate_hours, unit=AssignedTimeUnit.HOURS),
        _assigned(value=compared_minutes),
    )
    evidence = {item.key: item.value for item in result.evidence}

    assert result.outcome == expected
    assert evidence["candidate-normalized-minutes"] == str(
        candidate_hours * Decimal("60")
    )


@pytest.mark.parametrize(
    ("candidate_assigned", "compared_assigned"),
    (
        (
            _assigned(
                status=AssignedTimeStatus.PARTIAL,
                value=Decimal("10"),
            ),
            _assigned(value=Decimal("120")),
        ),
        (
            _assigned(status=AssignedTimeStatus.UNKNOWN, value=None, unit=None),
            _assigned(value=Decimal("120")),
        ),
        (
            _assigned(value=Decimal("120")),
            _assigned(
                status=AssignedTimeStatus.PARTIAL,
                value=Decimal("10"),
            ),
        ),
        (
            _assigned(value=Decimal("120")),
            _assigned(status=AssignedTimeStatus.UNKNOWN, value=None, unit=None),
        ),
        (
            _assigned(status=AssignedTimeStatus.UNKNOWN, value=None, unit=None),
            _assigned(status=AssignedTimeStatus.UNKNOWN, value=None, unit=None),
        ),
    ),
)
def test_partial_or_unknown_load_makes_comparison_neutral(
    candidate_assigned,
    compared_assigned,
):
    result = _evaluate(candidate_assigned, compared_assigned)

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert result.message == (
        "Weekly load comparison is unavailable because assigned time "
        "is partial or unknown."
    )


def test_partial_quantity_is_preserved_but_not_normalized_as_total():
    result = _evaluate(
        _assigned(
            status=AssignedTimeStatus.PARTIAL,
            value=Decimal("120"),
        ),
        _assigned(value=Decimal("240")),
    )
    evidence = {item.key: item.value for item in result.evidence}

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert evidence["candidate-assigned-quantity"] == "120"
    assert evidence["candidate-normalized-minutes"] is None


def test_unknown_load_is_not_treated_as_zero():
    result = _evaluate(
        _assigned(status=AssignedTimeStatus.UNKNOWN, value=None, unit=None),
        _assigned(value=Decimal("120")),
    )
    evidence = {item.key: item.value for item in result.evidence}

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert evidence["candidate-assigned-quantity"] is None
    assert evidence["candidate-normalized-minutes"] is None


def test_explicit_priority_is_preserved_and_validated_by_contract():
    result = _evaluate(
        _assigned(value=Decimal("120")),
        _assigned(value=Decimal("240")),
        priority=7,
    )

    assert result.priority == 7
    with pytest.raises(ValidationError):
        _evaluate(
            _assigned(value=Decimal("120")),
            _assigned(value=Decimal("240")),
            priority=True,
        )


def test_evidence_and_output_are_deterministic_and_immutable():
    candidate = _assigned(value=Decimal("120"))
    compared = _assigned(value=Decimal("240"))

    first = _evaluate(candidate, compared)
    second = _evaluate(candidate, compared)

    assert first == second
    assert first.evidence == second.evidence
    with pytest.raises(ValidationError):
        first.outcome = PlanningPreferenceOutcome.NEUTRAL
    with pytest.raises(TypeError):
        first.evidence[0] = first.evidence[0]


def test_module_is_pure_neutral_and_contains_no_ranking_or_scoring():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "lower_weekly_load_preference.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "repository",
        "sqlalchemy",
        "fastapi",
        "weekly_hours",
        "employment_type",
        "is_reserve",
        "recent_consecutivity",
        "availability",
        "already_approved_assignments",
        "score",
        "weighted",
        "sorted(",
        ".sort(",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import HumanResource, OperationalUnit
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    CurrentMemberContractStateSnapshot,
    PlanningPreferenceOutcome,
    WorkforceCandidateSnapshot,
    evaluate_continuity_preference,
)


UNIT = OperationalUnit(external_identifier="unit-one")


def _candidate(
    identifier: str,
    recent_consecutivity: int | None,
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
        recent_consecutivity=recent_consecutivity,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.UNKNOWN
        ),
    )


def _evaluate(
    candidate_consecutivity: int | None,
    compared_consecutivity: int | None,
    *,
    priority: int = 4,
):
    return evaluate_continuity_preference(
        candidate=_candidate("candidate-one", candidate_consecutivity),
        compared_candidate=_candidate(
            "candidate-two",
            compared_consecutivity,
        ),
        priority=priority,
    )


@pytest.mark.parametrize(
    ("candidate_value", "compared_value", "expected"),
    (
        (1, 3, PlanningPreferenceOutcome.PREFERRED),
        (3, 1, PlanningPreferenceOutcome.DEPRIORITIZED),
        (2, 2, PlanningPreferenceOutcome.NEUTRAL),
        (0, 1, PlanningPreferenceOutcome.PREFERRED),
    ),
)
def test_known_consecutivity_produces_expected_relative_outcome(
    candidate_value,
    compared_value,
    expected,
):
    result = _evaluate(candidate_value, compared_value)

    assert result.outcome == expected
    assert result.code == "continuity"
    assert result.rule_origin == "core-policy"


@pytest.mark.parametrize(
    ("candidate_value", "compared_value"),
    (
        (None, 1),
        (1, None),
        (None, None),
    ),
)
def test_unknown_consecutivity_makes_comparison_neutral(
    candidate_value,
    compared_value,
):
    result = _evaluate(candidate_value, compared_value)

    assert result.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert result.message == (
        "Continuity comparison is unavailable because recent "
        "consecutivity is unknown."
    )


def test_unknown_is_preserved_and_not_interpreted_as_zero():
    unknown = _evaluate(None, 1)
    known_zero = _evaluate(0, 1)
    unknown_evidence = {item.key: item.value for item in unknown.evidence}

    assert unknown.outcome == PlanningPreferenceOutcome.NEUTRAL
    assert known_zero.outcome == PlanningPreferenceOutcome.PREFERRED
    assert unknown_evidence["candidate-recent-consecutivity"] is None


def test_explicit_priority_is_preserved_and_validated_by_contract():
    result = _evaluate(1, 3, priority=9)

    assert result.priority == 9
    with pytest.raises(ValidationError):
        _evaluate(1, 3, priority=True)


def test_evidence_and_output_are_deterministic_and_immutable():
    first = _evaluate(1, 3)
    second = _evaluate(1, 3)

    assert first == second
    assert first.evidence == second.evidence
    assert [item.value for item in first.evidence] == [1, 3]
    with pytest.raises(ValidationError):
        first.outcome = PlanningPreferenceOutcome.NEUTRAL
    with pytest.raises(TypeError):
        first.evidence[0] = first.evidence[0]


def test_module_has_no_thresholds_recalculation_ranking_or_external_dependencies():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "continuity_preference.py"
    )
    source_text = module_path.read_text(encoding="utf-8")
    source = source_text.casefold()
    numeric_constants = {
        node.value
        for node in ast.walk(ast.parse(source_text))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    }
    forbidden_fragments = (
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "repository",
        "sqlalchemy",
        "fastapi",
        "availability",
        "callability",
        "assigned_time",
        "weekly_hours",
        "employment_type",
        "already_approved_assignments",
        "capability",
        "score",
        "weighted",
        "sorted(",
        ".sort(",
        "mandatory",
        "warning",
    )

    assert numeric_constants == set()
    assert source.count(".recent_consecutivity") == 2
    assert all(fragment not in source for fragment in forbidden_fragments)

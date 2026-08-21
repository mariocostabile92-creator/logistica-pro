from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    ConstraintEvidence,
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
    WorkforcePlanningPreferenceSet,
)


def _evaluation(
    *,
    code: str = "lower-weekly-load",
    outcome: PlanningPreferenceOutcome = PlanningPreferenceOutcome.PREFERRED,
    priority: int = 0,
    message: str = "Candidate has a favorable deterministic preference.",
    rule_origin: str = "organization-policy",
) -> PlanningPreferenceEvaluation:
    return PlanningPreferenceEvaluation(
        code=code,
        outcome=outcome,
        priority=priority,
        message=message,
        evidence=(
            ConstraintEvidence(
                key="deterministic-input",
                value="opaque-value",
            ),
        ),
        rule_origin=rule_origin,
    )


@pytest.mark.parametrize(
    "outcome",
    (
        PlanningPreferenceOutcome.PREFERRED,
        PlanningPreferenceOutcome.NEUTRAL,
        PlanningPreferenceOutcome.DEPRIORITIZED,
    ),
)
def test_all_preference_outcomes_are_representable(outcome):
    evaluation = _evaluation(outcome=outcome)

    assert evaluation.outcome == outcome


@pytest.mark.parametrize("priority", (0, 1, 99))
def test_non_negative_strict_integer_priority_is_valid(priority):
    evaluation = _evaluation(priority=priority)

    assert evaluation.priority == priority


def test_negative_priority_is_rejected():
    with pytest.raises(ValidationError):
        _evaluation(priority=-1)


def test_boolean_priority_is_rejected():
    with pytest.raises(ValidationError):
        _evaluation(priority=True)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("code", " "),
        ("message", " "),
        ("rule_origin", " "),
    ),
)
def test_required_text_fields_reject_empty_or_whitespace(field, value):
    with pytest.raises(ValidationError):
        _evaluation(**{field: value})


def test_invalid_outcome_is_rejected():
    with pytest.raises(ValidationError):
        _evaluation(outcome="UNKNOWN")


def test_evidence_reuses_existing_constraint_evidence():
    evaluation = _evaluation()

    assert isinstance(evaluation.evidence[0], ConstraintEvidence)
    assert evaluation.evidence[0].key == "deterministic-input"


def test_preference_set_and_nested_collections_are_immutable():
    evaluation = _evaluation()
    preference_set = WorkforcePlanningPreferenceSet(
        demand_trace_id="demand-trace-one",
        workforce_member_id="opaque-member-42",
        operational_date=date(2026, 8, 24),
        evaluations=(evaluation,),
    )

    with pytest.raises(ValidationError):
        evaluation.outcome = PlanningPreferenceOutcome.NEUTRAL
    with pytest.raises(TypeError):
        evaluation.evidence[0] = evaluation.evidence[0]
    with pytest.raises(ValidationError):
        preference_set.workforce_member_id = "changed"
    with pytest.raises(TypeError):
        preference_set.evaluations[0] = evaluation


def test_preference_set_requires_non_empty_demand_trace() -> None:
    with pytest.raises(ValidationError):
        WorkforcePlanningPreferenceSet(
            demand_trace_id=" ",
            workforce_member_id="opaque-member-42",
            operational_date=date(2026, 8, 24),
        )


def test_deprioritized_is_only_an_outcome_and_does_not_change_eligibility():
    evaluation = _evaluation(
        outcome=PlanningPreferenceOutcome.DEPRIORITIZED
    )

    assert evaluation.outcome == PlanningPreferenceOutcome.DEPRIORITIZED
    assert "eligible" not in PlanningPreferenceEvaluation.model_fields


@pytest.mark.parametrize(
    "code",
    (
        "lower-weekly-load",
        "continuity",
        "existing-assignment-stability",
        "configurable-policy-priority",
    ),
)
def test_future_preference_codes_are_representable_without_business_logic(code):
    assert _evaluation(code=code).code == code


def test_same_logical_input_is_deterministic():
    first = _evaluation()
    second = _evaluation()

    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_contract_is_neutral_pure_and_contains_no_numeric_scoring():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "planning_preference.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "repository",
        "sqlalchemy",
        "fastapi",
        "score:",
        "weighted",
        "__lt__",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

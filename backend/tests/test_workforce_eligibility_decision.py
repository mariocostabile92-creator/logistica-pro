from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
    EligibilityDecisionNotice,
    WorkforceEligibilityDecision,
)


UNIT = OperationalUnit(external_identifier="unit-north", name="North Hub")
WINDOW = TimeWindow(
    external_identifier="morning-window",
    starts_at="08:00",
    ends_at="12:00",
)


def _evaluation(*, passed: bool = True) -> ConstraintEvaluation:
    return ConstraintEvaluation(
        code="availability-check",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=passed,
        message="Candidate availability was evaluated.",
        evidence=(ConstraintEvidence(key="available", value=passed),),
        rule_origin="core-policy",
    )


def _decision(**updates) -> WorkforceEligibilityDecision:
    payload = {
        "organization_id": "organization-one",
        "workforce_member_id": "opaque-member-42",
        "operational_date": date(2026, 8, 24),
        "operational_unit": UNIT,
        "time_window": WINDOW,
        "capability_or_workload": "generic-delivery-capability",
        "eligible": True,
        "evaluations": (_evaluation(),),
        "warnings": (
            EligibilityDecisionNotice(
                code="review-context",
                message="Dispatcher review remains available.",
            ),
        ),
    }
    payload.update(updates)
    return WorkforceEligibilityDecision(**payload)


def test_eligible_decision_preserves_scope_and_opaque_identity():
    decision = _decision()

    assert decision.organization_id == "organization-one"
    assert decision.workforce_member_id == "opaque-member-42"
    assert decision.operational_date == date(2026, 8, 24)
    assert decision.operational_unit == UNIT
    assert decision.time_window == WINDOW
    assert decision.capability_or_workload == "generic-delivery-capability"
    assert decision.eligible is True


def test_non_eligible_decision_supports_structured_exclusion_reasons():
    reason = EligibilityDecisionNotice(
        code="not-available",
        message="Candidate is not available in this time window.",
    )
    decision = _decision(
        eligible=False,
        evaluations=(_evaluation(passed=False),),
        exclusion_reasons=(reason,),
    )

    assert decision.eligible is False
    assert decision.exclusion_reasons == (reason,)
    assert decision.evaluations[0].passed is False


@pytest.mark.parametrize("invalid", [1, 0, "true", None])
def test_eligible_requires_a_strict_boolean(invalid):
    with pytest.raises(ValidationError):
        _decision(eligible=invalid)


def test_evaluations_reuse_constraint_evaluation_and_are_immutable():
    evaluation = _evaluation()
    decision = _decision(evaluations=[evaluation])

    assert decision.evaluations == (evaluation,)
    assert isinstance(decision.evaluations[0], ConstraintEvaluation)
    with pytest.raises(TypeError):
        decision.evaluations[0] = evaluation


def test_exclusion_reasons_and_warnings_are_structured_and_immutable():
    reason = EligibilityDecisionNotice(
        code="excluded",
        message="Candidate was excluded.",
    )
    warning = EligibilityDecisionNotice(
        code="review",
        message="Review this decision.",
    )
    decision = _decision(
        eligible=False,
        exclusion_reasons=[reason],
        warnings=[warning],
    )

    assert decision.exclusion_reasons == (reason,)
    assert decision.warnings == (warning,)
    with pytest.raises(TypeError):
        decision.exclusion_reasons[0] = reason
    with pytest.raises(ValidationError):
        warning.message = "Changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("code", "   "),
        ("message", ""),
        ("message", "   "),
    ],
)
def test_notice_rejects_empty_code_or_message(field, value):
    payload = {"code": "notice", "message": "A structured notice."}
    payload[field] = value

    with pytest.raises(ValidationError):
        EligibilityDecisionNotice(**payload)


def test_eligible_decision_rejects_exclusion_reasons():
    with pytest.raises(
        ValidationError,
        match="eligible decision cannot include exclusion reasons",
    ):
        _decision(
            exclusion_reasons=(
                EligibilityDecisionNotice(
                    code="incoherent",
                    message="This would exclude the candidate.",
                ),
            )
        )


def test_non_eligible_decision_without_exclusion_reasons_remains_valid():
    decision = _decision(eligible=False, exclusion_reasons=())

    assert decision.eligible is False
    assert decision.exclusion_reasons == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("organization_id", " "),
        ("workforce_member_id", " "),
        ("capability_or_workload", " "),
    ],
)
def test_required_text_fields_reject_empty_values(field, value):
    with pytest.raises(ValidationError):
        _decision(**{field: value})


def test_operational_unit_must_have_a_canonical_identifier():
    invalid_unit = OperationalUnit(external_identifier=" ")

    with pytest.raises(ValidationError, match="operational_unit cannot be empty"):
        _decision(operational_unit=invalid_unit)


def test_decision_is_immutable():
    decision = _decision()

    with pytest.raises(ValidationError):
        decision.eligible = False


def test_core_contract_contains_no_vertical_or_asset_terminology():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "workforce_eligibility_decision.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = ("amazon", "dsp", "fleet", "vehicle")
    assert all(fragment not in source for fragment in forbidden_fragments)

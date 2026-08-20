from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
    ConstraintRemediation,
)
from app.domain.workforce_auto_planning import (
    constraint_evaluation as evaluation_module,
)


def _evidence(**overrides: object) -> ConstraintEvidence:
    values: dict[str, object] = {
        "key": "available_hours",
        "value": 8,
    }
    values.update(overrides)
    return ConstraintEvidence.model_validate(values)


def _remediation(**overrides: object) -> ConstraintRemediation:
    values: dict[str, object] = {
        "code": "REVIEW_AVAILABILITY",
        "message": "Review the declared availability window.",
    }
    values.update(overrides)
    return ConstraintRemediation.model_validate(values)


def _evaluation(**overrides: object) -> ConstraintEvaluation:
    values: dict[str, object] = {
        "code": "AVAILABILITY_WINDOW",
        "category": ConstraintEvaluationCategory.HARD_CONSTRAINT,
        "passed": True,
        "message": "The resource is available for the requested window.",
        "evidence": (_evidence(),),
        "rule_origin": "core-policy",
        "remediation": None,
    }
    values.update(overrides)
    return ConstraintEvaluation.model_validate(values)


@pytest.mark.parametrize("category", tuple(ConstraintEvaluationCategory))
def test_all_declared_categories_are_representable(
    category: ConstraintEvaluationCategory,
) -> None:
    assert _evaluation(category=category).category is category


@pytest.mark.parametrize("passed", (True, False))
def test_passed_and_failed_results_are_representable(passed: bool) -> None:
    assert _evaluation(passed=passed).passed is passed


@pytest.mark.parametrize("passed", (1, 0, "true", None))
def test_passed_must_be_a_strict_boolean(passed: object) -> None:
    with pytest.raises(ValidationError):
        _evaluation(passed=passed)


def test_evidence_is_structured_and_immutable() -> None:
    evaluation = _evaluation()
    evidence = evaluation.evidence[0]

    assert evidence.key == "available_hours"
    assert evidence.value == 8
    assert isinstance(evaluation.evidence, tuple)
    with pytest.raises(ValidationError):
        evidence.key = "changed"


def test_empty_evidence_collection_is_valid() -> None:
    assert _evaluation(evidence=()).evidence == ()


@pytest.mark.parametrize("value", ({"nested": True}, [1], (1,), object()))
def test_complex_evidence_values_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        _evidence(value=value)


def test_evidence_key_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        _evidence(key=" ")


def test_remediation_can_be_absent() -> None:
    assert _evaluation(remediation=None).remediation is None


def test_valid_remediation_is_structured_and_immutable() -> None:
    evaluation = _evaluation(remediation=_remediation())

    assert evaluation.remediation is not None
    assert evaluation.remediation.code == "REVIEW_AVAILABILITY"
    with pytest.raises(ValidationError):
        evaluation.remediation.message = "changed"


@pytest.mark.parametrize("field", ("code", "message"))
def test_remediation_fields_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _remediation(**{field: " "})


def test_rule_origin_is_required_and_validated() -> None:
    with pytest.raises(ValidationError):
        _evaluation(rule_origin=" ")


@pytest.mark.parametrize("field", ("code", "message"))
def test_evaluation_required_text_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _evaluation(**{field: " "})


def test_category_outside_declared_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _evaluation(category="OTHER")


def test_evaluation_is_immutable() -> None:
    evaluation = _evaluation()

    with pytest.raises(ValidationError):
        evaluation.passed = False


def test_contract_has_no_vertical_or_fleet_terminology() -> None:
    source = getsource(evaluation_module).casefold()

    assert "amazon" not in source
    assert "dsp" not in source
    assert "vehicle" not in source
    assert "fleet" not in source

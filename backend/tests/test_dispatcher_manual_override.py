from datetime import datetime, timezone
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    ConstraintEvidence,
    DispatcherManualOverride,
    DispatcherOverrideOperationType,
)
from app.domain.workforce_auto_planning import dispatcher_manual_override


CREATED_AT = datetime(2026, 8, 23, 9, 30, tzinfo=timezone.utc)


def _violation(code: str) -> ConstraintEvaluation:
    return ConstraintEvaluation(
        code=code,
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=False,
        message=f"Failed constraint: {code}.",
        evidence=(ConstraintEvidence(key="authoritative", value=True),),
        rule_origin="core-policy",
    )


def _override(**updates: object) -> DispatcherManualOverride:
    values: dict[str, object] = {
        "override_id": "override-one",
        "organization_id": "organization-one",
        "proposal_id": "proposal-one",
        "proposal_version": 2,
        "assignment_id": None,
        "operation_type": DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        "reason": "Operational need agreed by dispatcher.",
        "actor_id": "dispatcher-one",
        "violations": (),
        "created_at": CREATED_AT,
    }
    values.update(updates)
    return DispatcherManualOverride(**values)


def test_add_assignment_accepts_missing_assignment_reference() -> None:
    override = _override()
    assert override.operation_type is DispatcherOverrideOperationType.ADD_ASSIGNMENT
    assert override.assignment_id is None


def test_add_assignment_accepts_failed_business_violations() -> None:
    violations = (
        _violation("weekly-hours-capacity"),
        _violation("daily-callability"),
        _violation("approved-assignment-conflict"),
        _violation("capability-compatibility"),
    )
    override = _override(violations=violations)

    assert override.violations == violations
    assert all(not item.passed for item in override.violations)
    assert "eligible" not in DispatcherManualOverride.model_fields
    assert "status" not in DispatcherManualOverride.model_fields


@pytest.mark.parametrize(
    "operation_type",
    (
        DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
        DispatcherOverrideOperationType.REPLACE_ASSIGNMENT,
        DispatcherOverrideOperationType.MOVE_ASSIGNMENT,
        DispatcherOverrideOperationType.MODIFY_ASSIGNMENT,
    ),
)
def test_existing_assignment_operations_require_assignment_id(
    operation_type: DispatcherOverrideOperationType,
) -> None:
    with pytest.raises(ValidationError, match="requires assignment_id"):
        _override(operation_type=operation_type, assignment_id=None)


@pytest.mark.parametrize("assignment_id", ("", "   "))
def test_blank_assignment_id_is_rejected_when_present(
    assignment_id: str,
) -> None:
    with pytest.raises(ValidationError):
        _override(assignment_id=assignment_id)


@pytest.mark.parametrize(
    "operation_type",
    tuple(DispatcherOverrideOperationType),
)
def test_all_operation_types_are_representable_with_valid_references(
    operation_type: DispatcherOverrideOperationType,
) -> None:
    override = _override(
        operation_type=operation_type,
        assignment_id=(
            None
            if operation_type is DispatcherOverrideOperationType.ADD_ASSIGNMENT
            else "assignment-one"
        ),
    )
    assert override.operation_type is operation_type


@pytest.mark.parametrize(
    "field",
    ("override_id", "organization_id", "proposal_id", "actor_id", "reason"),
)
@pytest.mark.parametrize("value", ("", "   "))
def test_required_text_fields_reject_blank_values(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        _override(**{field: value})


@pytest.mark.parametrize("proposal_version", (0, -1, True))
def test_proposal_version_is_a_strict_positive_integer(
    proposal_version: object,
) -> None:
    with pytest.raises(ValidationError):
        _override(proposal_version=proposal_version)


@pytest.mark.parametrize(
    "code",
    (
        "weekly-hours-capacity",
        "daily-callability",
        "approved-assignment-conflict",
        "capability-compatibility",
        "contract-date-validity",
        "operational-unit-match",
    ),
)
def test_failed_constraint_is_valid_audit_data_without_invalidating_override(
    code: str,
) -> None:
    violation = _violation(code)
    override = _override(violations=(violation,))
    assert override.violations == (violation,)


def test_passed_constraint_cannot_be_stored_as_a_violation() -> None:
    passed = _violation("daily-callability").model_copy(
        update={"passed": True}
    )
    with pytest.raises(ValidationError, match="only failed constraints"):
        _override(violations=(passed,))


def test_model_and_violations_collection_are_immutable() -> None:
    override = _override(violations=(_violation("daily-callability"),))
    with pytest.raises(ValidationError):
        override.reason = "Changed"
    with pytest.raises(TypeError):
        override.violations[0] = _violation("other")


def test_created_at_is_caller_supplied_and_preserved() -> None:
    override = _override(created_at=CREATED_AT)
    assert override.created_at == CREATED_AT


def test_contract_has_no_clock_persistence_vertical_or_execution_semantics() -> None:
    source = getsource(dispatcher_manual_override).casefold()
    forbidden = (
        "datetime.now",
        "utcnow",
        "db_session",
        "repository",
        "sql",
        "fastapi",
        "amazon",
        "dsp",
        "fleet",
        "approve",
        "publish",
        "regenerate",
        "lock",
    )
    assert all(term not in source for term in forbidden)

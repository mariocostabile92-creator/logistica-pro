from datetime import date
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
)
from app.domain.workforce_auto_planning import (
    proposed_shift_assignment as assignment_module,
)


def _reason(**overrides: object) -> ProposedAssignmentReason:
    values: dict[str, object] = {
        "code": "CAPABILITY_MATCH",
        "message": "Member capability matches the requested workload.",
    }
    values.update(overrides)
    return ProposedAssignmentReason.model_validate(values)


def _assignment(**overrides: object) -> ProposedShiftAssignment:
    values: dict[str, object] = {
        "assignment_id": "assignment-2026-08-24-member-42",
        "organization_id": "organization-one",
        "workforce_member_id": "member-42",
        "date": date(2026, 8, 24),
        "operational_unit": OperationalUnit(
            external_identifier="unit-north",
            name="North depot",
        ),
        "shift_identifier": "early-shift",
        "time_window": TimeWindow(
            external_identifier="early-window",
            starts_at="06:00",
            ends_at="14:00",
        ),
        "capability_or_workload": "parcel-delivery",
        "origin": ProposedShiftAssignmentOrigin.AUTOMATIC,
        "status": ProposedShiftAssignmentStatus.PROPOSED,
        "deterministic_priority": 10,
        "reasons": (_reason(),),
        "locked": False,
    }
    values.update(overrides)
    return ProposedShiftAssignment.model_validate(values)


def test_valid_proposed_shift_assignment_can_be_created() -> None:
    assignment = _assignment()

    assert assignment.assignment_id == "assignment-2026-08-24-member-42"
    assert assignment.workforce_member_id == "member-42"
    assert assignment.shift_identifier == "early-shift"
    assert assignment.deterministic_priority == 10


def test_unknown_shift_identifier_is_valid_without_fallback() -> None:
    assignment = _assignment(shift_identifier=None)

    assert assignment.shift_identifier is None
    assert assignment.model_dump()["shift_identifier"] is None


@pytest.mark.parametrize("origin", tuple(ProposedShiftAssignmentOrigin))
def test_all_origins_are_representable(
    origin: ProposedShiftAssignmentOrigin,
) -> None:
    assert _assignment(origin=origin).origin is origin


@pytest.mark.parametrize("status", tuple(ProposedShiftAssignmentStatus))
def test_all_statuses_are_representable(
    status: ProposedShiftAssignmentStatus,
) -> None:
    assert _assignment(status=status).status is status


@pytest.mark.parametrize("locked", (False, True))
def test_locked_is_only_an_explicit_model_state(locked: bool) -> None:
    assert _assignment(locked=locked).locked is locked


def test_reasons_are_structured_and_immutable() -> None:
    assignment = _assignment()
    reason = assignment.reasons[0]

    assert reason.code == "CAPABILITY_MATCH"
    assert reason.message == (
        "Member capability matches the requested workload."
    )
    assert isinstance(assignment.reasons, tuple)
    with pytest.raises(ValidationError):
        reason.code = "CHANGED"


@pytest.mark.parametrize("priority", (-1, True, "1", 1.5))
def test_deterministic_priority_is_a_non_negative_strict_integer(
    priority: object,
) -> None:
    with pytest.raises(ValidationError):
        _assignment(deterministic_priority=priority)


@pytest.mark.parametrize(
    "field",
    (
        "assignment_id",
        "organization_id",
        "workforce_member_id",
        "capability_or_workload",
    ),
)
def test_required_identifiers_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _assignment(**{field: " "})


@pytest.mark.parametrize("value", ("", " ", "   "))
def test_known_shift_identifier_cannot_be_empty(value: str) -> None:
    with pytest.raises(ValidationError):
        _assignment(shift_identifier=value)


@pytest.mark.parametrize("field", ("code", "message"))
def test_reason_fields_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _reason(**{field: " "})


def test_at_least_one_reason_is_required() -> None:
    with pytest.raises(ValidationError):
        _assignment(reasons=())


def test_operational_unit_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="operational_unit cannot be empty"):
        _assignment(
            operational_unit=OperationalUnit(external_identifier=" ")
        )


def test_organization_id_is_preserved() -> None:
    assert _assignment(organization_id="organization-two").organization_id == (
        "organization-two"
    )


def test_assignment_is_immutable() -> None:
    assignment = _assignment()

    with pytest.raises(ValidationError):
        assignment.locked = True


def test_assignment_contract_has_no_vertical_or_fleet_terminology() -> None:
    source = getsource(assignment_module).casefold()

    assert "amazon" not in source
    assert "dsp" not in source
    assert "vehicle" not in source
    assert "fleet" not in source

from datetime import date
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import CoverageGap, CoverageGapReason
from app.domain.workforce_auto_planning import coverage_gap as gap_module


def _reason(**overrides: object) -> CoverageGapReason:
    values: dict[str, object] = {
        "code": "INSUFFICIENT_ELIGIBLE_RESOURCES",
        "message": "Eligible proposed resources do not cover demand.",
    }
    values.update(overrides)
    return CoverageGapReason.model_validate(values)


def _gap(**overrides: object) -> CoverageGap:
    values: dict[str, object] = {
        "demand_trace_id": "demand-trace-one",
        "organization_id": "organization-one",
        "date": date(2026, 8, 24),
        "operational_unit": OperationalUnit(
            external_identifier="unit-north",
            name="North depot",
        ),
        "time_window": TimeWindow(
            external_identifier="early-window",
            starts_at="06:00",
            ends_at="14:00",
        ),
        "capability_or_workload": "parcel-delivery",
        "required_quantity": 12,
        "proposed_quantity": 9,
        "gap_quantity": 3,
        "reason": _reason(),
        "excluded_candidate_categories": (
            "unavailable",
            "missing_capability",
        ),
    }
    values.update(overrides)
    return CoverageGap.model_validate(values)


def test_positive_gap_represents_a_shortage() -> None:
    gap = _gap(
        required_quantity=12,
        proposed_quantity=9,
        gap_quantity=3,
    )

    assert gap.gap_quantity == 3


def test_zero_gap_represents_exact_coverage() -> None:
    gap = _gap(
        required_quantity=12,
        proposed_quantity=12,
        gap_quantity=0,
    )

    assert gap.gap_quantity == 0


def test_negative_gap_represents_a_surplus() -> None:
    gap = _gap(
        required_quantity=12,
        proposed_quantity=15,
        gap_quantity=-3,
    )

    assert gap.gap_quantity == -3


def test_incoherent_gap_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            "gap_quantity must equal required_quantity - "
            "proposed_quantity"
        ),
    ):
        _gap(gap_quantity=2)


def test_reason_is_structured_and_immutable() -> None:
    gap = _gap()

    assert gap.reason.code == "INSUFFICIENT_ELIGIBLE_RESOURCES"
    assert gap.reason.message == (
        "Eligible proposed resources do not cover demand."
    )
    with pytest.raises(ValidationError):
        gap.reason.code = "CHANGED"


def test_excluded_candidate_categories_are_immutable() -> None:
    gap = _gap()

    assert isinstance(gap.excluded_candidate_categories, tuple)
    assert gap.excluded_candidate_categories == (
        "unavailable",
        "missing_capability",
    )
    with pytest.raises(ValidationError):
        gap.excluded_candidate_categories = ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("required_quantity", -1),
        ("proposed_quantity", -1),
        ("required_quantity", True),
        ("proposed_quantity", "9"),
    ),
)
def test_quantities_are_non_negative_strict_integers(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        _gap(**{field: value})


@pytest.mark.parametrize("field", ("code", "message"))
def test_reason_fields_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _reason(**{field: " "})


@pytest.mark.parametrize("category", ("", "   "))
def test_excluded_candidate_category_cannot_be_empty(category: str) -> None:
    with pytest.raises(
        ValidationError,
        match="excluded candidate category cannot be empty",
    ):
        _gap(excluded_candidate_categories=(category,))


def test_empty_excluded_candidate_collection_is_valid() -> None:
    assert _gap(excluded_candidate_categories=()).excluded_candidate_categories == ()


def test_organization_id_is_preserved() -> None:
    assert _gap(organization_id="organization-two").organization_id == (
        "organization-two"
    )


@pytest.mark.parametrize(
    "field",
    ("demand_trace_id", "organization_id", "capability_or_workload"),
)
def test_required_identifiers_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _gap(**{field: " "})


def test_operational_unit_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="operational_unit cannot be empty"):
        _gap(
            operational_unit=OperationalUnit(external_identifier=" ")
        )


def test_gap_model_is_immutable() -> None:
    gap = _gap()

    with pytest.raises(ValidationError):
        gap.gap_quantity = 0


def test_gap_contract_has_no_vertical_or_fleet_terminology() -> None:
    source = getsource(gap_module).casefold()

    assert "amazon" not in source
    assert "dsp" not in source
    assert "vehicle" not in source
    assert "fleet" not in source

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    ContractDateEligibilityStatus,
    CurrentMemberContractStateSnapshot,
    evaluate_contract_date_eligibility,
)


OPERATIONAL_DATE = date(2026, 8, 21)


def _evaluate(
    *,
    contract_start: date | None = None,
    contract_end: date | None = None,
    employment_type: str | None = None,
    weekly_hours: Decimal | None = None,
    is_reserve: bool | None = None,
):
    return evaluate_contract_date_eligibility(
        contract_state=CurrentMemberContractStateSnapshot(
            contract_start=contract_start,
            contract_end=contract_end,
            employment_type=employment_type,
            weekly_hours=weekly_hours,
            is_reserve=is_reserve,
        ),
        operational_date=OPERATIONAL_DATE,
    )


def test_absent_start_and_end_are_eligible_without_invented_limits():
    result = _evaluate()
    evidence = {item.key: item.value for item in result.evidence}

    assert result.status == ContractDateEligibilityStatus.ELIGIBLE
    assert result.contract_start is None
    assert result.contract_end is None
    assert result.reason.code == "no-contract-date-limits"
    assert evidence["contract-start"] is None
    assert evidence["contract-end"] is None


@pytest.mark.parametrize(
    ("contract_start", "expected_status", "expected_reason"),
    (
        (
            date(2026, 8, 22),
            ContractDateEligibilityStatus.INELIGIBLE,
            "before-contract-start",
        ),
        (
            OPERATIONAL_DATE,
            ContractDateEligibilityStatus.ELIGIBLE,
            "contract-date-valid",
        ),
        (
            date(2026, 8, 20),
            ContractDateEligibilityStatus.ELIGIBLE,
            "contract-date-valid",
        ),
    ),
)
def test_start_only_uses_an_inclusive_lower_bound(
    contract_start,
    expected_status,
    expected_reason,
):
    result = _evaluate(contract_start=contract_start)

    assert result.status == expected_status
    assert result.reason.code == expected_reason
    assert result.contract_end is None


@pytest.mark.parametrize(
    ("contract_end", "expected_status", "expected_reason"),
    (
        (
            date(2026, 8, 22),
            ContractDateEligibilityStatus.ELIGIBLE,
            "contract-date-valid",
        ),
        (
            OPERATIONAL_DATE,
            ContractDateEligibilityStatus.ELIGIBLE,
            "contract-date-valid",
        ),
        (
            date(2026, 8, 20),
            ContractDateEligibilityStatus.INELIGIBLE,
            "after-contract-end",
        ),
    ),
)
def test_end_only_uses_an_inclusive_upper_bound(
    contract_end,
    expected_status,
    expected_reason,
):
    result = _evaluate(contract_end=contract_end)

    assert result.status == expected_status
    assert result.reason.code == expected_reason
    assert result.contract_start is None


@pytest.mark.parametrize(
    ("contract_start", "contract_end", "expected_status", "expected_reason"),
    (
        (
            date(2026, 8, 20),
            date(2026, 8, 22),
            ContractDateEligibilityStatus.ELIGIBLE,
            "contract-date-valid",
        ),
        (
            date(2026, 8, 22),
            date(2026, 8, 23),
            ContractDateEligibilityStatus.INELIGIBLE,
            "before-contract-start",
        ),
        (
            date(2026, 8, 19),
            date(2026, 8, 20),
            ContractDateEligibilityStatus.INELIGIBLE,
            "after-contract-end",
        ),
    ),
)
def test_complete_interval_is_evaluated_against_both_limits(
    contract_start,
    contract_end,
    expected_status,
    expected_reason,
):
    result = _evaluate(
        contract_start=contract_start,
        contract_end=contract_end,
    )

    assert result.status == expected_status
    assert result.reason.code == expected_reason


@pytest.mark.parametrize(
    "contract_updates",
    (
        {"employment_type": "full-time"},
        {"employment_type": "part-time"},
        {"weekly_hours": Decimal("20")},
        {"weekly_hours": Decimal("40")},
        {"is_reserve": True},
        {"is_reserve": False},
    ),
)
def test_non_date_contract_attributes_do_not_change_result(contract_updates):
    baseline = _evaluate(
        contract_start=date(2026, 8, 20),
        contract_end=date(2026, 8, 22),
    )
    result = _evaluate(
        contract_start=date(2026, 8, 20),
        contract_end=date(2026, 8, 22),
        **contract_updates,
    )

    assert result == baseline


def test_result_is_deterministic_and_immutable():
    first = _evaluate(contract_start=date(2026, 8, 20))
    second = _evaluate(contract_start=date(2026, 8, 20))

    assert first == second
    with pytest.raises(ValidationError):
        first.status = ContractDateEligibilityStatus.INELIGIBLE
    with pytest.raises(ValidationError):
        first.reason.code = "changed"
    with pytest.raises(TypeError):
        first.evidence[0] = first.evidence[0]


def test_module_is_pure_and_neutral():
    domain_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
    )
    source = (domain_path / "contract_date_eligibility.py").read_text(
        encoding="utf-8"
    ).casefold()
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
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

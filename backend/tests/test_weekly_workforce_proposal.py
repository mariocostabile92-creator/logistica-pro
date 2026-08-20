from datetime import date, datetime, timezone
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)
from app.domain.workforce_auto_planning import (
    weekly_workforce_proposal as proposal_module,
)


def _proposal(**overrides: object) -> WeeklyWorkforceProposal:
    values: dict[str, object] = {
        "proposal_id": "proposal-2026-w35-v1",
        "organization_id": "organization-one",
        "period_start": date(2026, 8, 24),
        "period_end": date(2026, 8, 30),
        "operational_unit": OperationalUnit(
            external_identifier="unit-north",
            name="North depot",
        ),
        "version": 1,
        "input_fingerprint": "input-snapshot-fingerprint",
        "policy_set_identifier": "standard-weekly-policy",
        "policy_set_version": "v1",
        "status": WeeklyWorkforceProposalStatus.DRAFT,
        "created_at": datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return WeeklyWorkforceProposal.model_validate(values)


def test_valid_weekly_proposal_can_be_created() -> None:
    proposal = _proposal()

    assert proposal.proposal_id == "proposal-2026-w35-v1"
    assert proposal.period_start == date(2026, 8, 24)
    assert proposal.period_end == date(2026, 8, 30)
    assert proposal.operational_unit.external_identifier == "unit-north"
    assert proposal.status is WeeklyWorkforceProposalStatus.DRAFT


def test_organization_identity_keeps_proposals_distinct() -> None:
    first = _proposal(organization_id="organization-one")
    second = _proposal(organization_id="organization-two")

    assert first.organization_id != second.organization_id
    assert first != second


def test_period_end_cannot_precede_period_start() -> None:
    with pytest.raises(
        ValidationError,
        match="period_end cannot precede period_start",
    ):
        _proposal(
            period_start=date(2026, 8, 30),
            period_end=date(2026, 8, 24),
        )


@pytest.mark.parametrize("version", (0, -1))
def test_version_must_be_positive(version: int) -> None:
    with pytest.raises(ValidationError):
        _proposal(version=version)


@pytest.mark.parametrize(
    "field",
    (
        "proposal_id",
        "organization_id",
        "input_fingerprint",
        "policy_set_identifier",
        "policy_set_version",
    ),
)
def test_required_identity_and_policy_fields_cannot_be_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        _proposal(**{field: " "})


def test_operational_unit_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="operational_unit cannot be empty"):
        _proposal(
            operational_unit=OperationalUnit(external_identifier=" ")
        )


@pytest.mark.parametrize("status", tuple(WeeklyWorkforceProposalStatus))
def test_all_declared_lifecycle_statuses_are_representable(
    status: WeeklyWorkforceProposalStatus,
) -> None:
    assert _proposal(status=status).status is status


def test_proposal_is_immutable() -> None:
    proposal = _proposal()

    with pytest.raises(ValidationError):
        proposal.version = 2


def test_proposal_contract_has_no_vertical_terminology() -> None:
    source = getsource(proposal_module).casefold()

    assert "amazon" not in source
    assert "dsp" not in source

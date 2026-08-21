import json
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.database import db_session
from app.domain.workforce_auto_planning import (
    WeeklyWorkforceProposalEvent,
    WeeklyWorkforceProposalEventAlreadyExistsError,
    WeeklyWorkforceProposalEventOrganizationMismatchError,
    WeeklyWorkforceProposalEventRepository,
)
from app.repositories.weekly_workforce_proposal_event_repository import (
    SqlWeeklyWorkforceProposalEventRepository,
    WeeklyWorkforceProposalEventRevisionNotFoundError,
)
from app.repositories.weekly_workforce_proposal_repository import (
    SqlWeeklyWorkforceProposalRepository,
)
from app.repositories.weekly_workforce_proposal_schema import init_schema
from tests.test_weekly_workforce_proposal_repository import _build_revision


TABLES = (
    "weekly_workforce_proposal_events",
    "weekly_workforce_proposal_explainability",
    "weekly_workforce_proposal_gaps",
    "weekly_workforce_proposal_assignments",
    "weekly_workforce_proposals",
    "weekly_planning_input_snapshots",
)
CREATED_AT = datetime(2026, 8, 21, 15, tzinfo=timezone.utc)


class _EventPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation: str
    violations: tuple[str, ...] = ()


class _MutableEventPayload(BaseModel):
    operation: str


@pytest.fixture(autouse=True)
def reset_proposal_tables() -> None:
    init_schema()
    with db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


def _event(
    *,
    organization_id: str = "organization-one",
    proposal_id: str = "proposal-one",
    proposal_version: int = 1,
    event_id: str = "event-one",
    actor_id: str | None = "dispatcher-one",
    reason: str | None = "Operational correction",
) -> WeeklyWorkforceProposalEvent:
    return WeeklyWorkforceProposalEvent(
        event_id=event_id,
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=proposal_version,
        event_type="GENERIC_PROPOSAL_EVENT",
        actor_id=actor_id,
        reason=reason,
        payload=_EventPayload(
            operation="generic-operation",
            violations=("constraint-one", "constraint-two"),
        ),
        created_at=CREATED_AT,
    )


def _save_revision(*, organization_id: str = "organization-one") -> None:
    snapshot, aggregate = _build_revision(organization_id=organization_id)
    SqlWeeklyWorkforceProposalRepository().save_revision(
        organization_id=organization_id,
        snapshot=snapshot,
        aggregate=aggregate,
    )


def test_event_model_is_typed_immutable_and_rejects_invalid_identity() -> None:
    event = _event()

    assert event.proposal_version == 1
    assert event.payload.operation == "generic-operation"
    with pytest.raises(ValidationError):
        event.event_id = "changed"
    with pytest.raises(ValidationError):
        _event(event_id=" ")
    with pytest.raises(ValidationError):
        WeeklyWorkforceProposalEvent(
            event_id="event",
            organization_id="organization-one",
            proposal_id="proposal-one",
            proposal_version=True,
            event_type="EVENT",
            payload=_EventPayload(operation="operation"),
            created_at=CREATED_AT,
        )
    with pytest.raises(ValidationError):
        WeeklyWorkforceProposalEvent(
            event_id="event",
            organization_id="organization-one",
            proposal_id="proposal-one",
            proposal_version=1,
            event_type="EVENT",
            payload=_MutableEventPayload(operation="operation"),
            created_at=CREATED_AT,
        )


def test_standalone_repository_implements_port_and_persists_canonical_payload() -> None:
    _save_revision()
    repository = SqlWeeklyWorkforceProposalEventRepository()
    event = _event()

    assert isinstance(repository, WeeklyWorkforceProposalEventRepository)
    assert repository.append_event(
        organization_id="organization-one",
        event=event,
    ) is event

    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM weekly_workforce_proposal_events
            WHERE organization_id = ? AND event_id = ?
            """,
            ("organization-one", "event-one"),
        ).fetchone()
    expected_payload = event.payload.model_dump(mode="json")
    assert json.loads(row["payload_json"]) == expected_payload
    assert row["payload_json"] == json.dumps(
        expected_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert row["actor_id"] == "dispatcher-one"
    assert row["reason"] == "Operational correction"
    assert row["created_at"] == CREATED_AT.isoformat()


def test_nullable_actor_and_reason_are_preserved() -> None:
    _save_revision()
    event = _event(actor_id=None, reason=None)

    SqlWeeklyWorkforceProposalEventRepository().append_event(
        organization_id="organization-one",
        event=event,
    )

    with db_session() as conn:
        row = conn.execute(
            "SELECT actor_id, reason FROM weekly_workforce_proposal_events"
        ).fetchone()
    assert row["actor_id"] is None
    assert row["reason"] is None


def test_organization_mismatch_duplicate_and_missing_revision_are_typed() -> None:
    _save_revision()
    repository = SqlWeeklyWorkforceProposalEventRepository()
    event = _event()

    with pytest.raises(WeeklyWorkforceProposalEventOrganizationMismatchError):
        repository.append_event(
            organization_id="organization-two",
            event=event,
        )

    repository.append_event(
        organization_id="organization-one",
        event=event,
    )
    with pytest.raises(WeeklyWorkforceProposalEventAlreadyExistsError):
        repository.append_event(
            organization_id="organization-one",
            event=event,
        )

    with pytest.raises(WeeklyWorkforceProposalEventRevisionNotFoundError):
        repository.append_event(
            organization_id="organization-one",
            event=_event(proposal_version=2, event_id="missing-revision"),
        )


def test_event_repository_is_strictly_organization_scoped() -> None:
    _save_revision(organization_id="organization-one")
    _save_revision(organization_id="organization-two")
    repository = SqlWeeklyWorkforceProposalEventRepository()
    first = _event(organization_id="organization-one", event_id="shared-event")
    second = _event(organization_id="organization-two", event_id="shared-event")

    repository.append_event(organization_id="organization-one", event=first)
    repository.append_event(organization_id="organization-two", event=second)

    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT organization_id FROM weekly_workforce_proposal_events
            WHERE event_id = ? ORDER BY organization_id
            """,
            ("shared-event",),
        ).fetchall()
    assert tuple(row["organization_id"] for row in rows) == (
        "organization-one",
        "organization-two",
    )

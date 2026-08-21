from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict

from app.core.database import db_session, get_connection
from app.domain.workforce_auto_planning import (
    WeeklyWorkforceProposalEvent,
    WeeklyWorkforceProposalEventAlreadyExistsError,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
)
from app.repositories.weekly_workforce_proposal_event_repository import (
    SqlWeeklyWorkforceProposalEventRepository,
)
from app.repositories.weekly_workforce_proposal_repository import (
    SqlWeeklyWorkforceProposalRepository,
)
from app.repositories.weekly_workforce_proposal_schema import init_schema
from app.repositories.weekly_workforce_proposal_unit_of_work import (
    WeeklyWorkforceProposalUnitOfWork,
)
from app.repositories import weekly_workforce_proposal_unit_of_work as uow_module
from tests.test_weekly_workforce_proposal_repository import _build_revision


TABLES = (
    "weekly_workforce_proposal_events",
    "weekly_workforce_proposal_explainability",
    "weekly_workforce_proposal_gaps",
    "weekly_workforce_proposal_assignments",
    "weekly_workforce_proposals",
    "weekly_planning_input_snapshots",
)


class _EventPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation: str


@pytest.fixture(autouse=True)
def reset_proposal_tables() -> None:
    init_schema()
    with db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


def _event(aggregate, *, event_id: str = "event-one"):
    proposal = aggregate.proposal
    return WeeklyWorkforceProposalEvent(
        event_id=event_id,
        organization_id=proposal.organization_id,
        proposal_id=proposal.proposal_id,
        proposal_version=proposal.version,
        event_type="GENERIC_PROPOSAL_EVENT",
        actor_id="dispatcher-one",
        reason="Operational correction",
        payload=_EventPayload(operation="generic-operation"),
        created_at=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
    )


def _count(table: str) -> int:
    with db_session() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int(row["total"])


def _save_with_event(uow, snapshot, aggregate, event) -> None:
    with uow.transaction() as tx:
        tx.proposals.save_revision(
            organization_id=snapshot.organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )
        tx.events.append_event(
            organization_id=snapshot.organization_id,
            event=event,
        )


def test_proposal_and_event_commit_atomically_with_all_children() -> None:
    snapshot, aggregate = _build_revision()
    event = _event(aggregate)

    _save_with_event(
        WeeklyWorkforceProposalUnitOfWork(),
        snapshot,
        aggregate,
        event,
    )

    assert _count("weekly_planning_input_snapshots") == 1
    assert _count("weekly_workforce_proposals") == 1
    assert _count("weekly_workforce_proposal_assignments") == len(
        aggregate.assignments
    )
    assert _count("weekly_workforce_proposal_gaps") == len(
        aggregate.coverage_gaps
    )
    assert _count("weekly_workforce_proposal_explainability") == (
        len(aggregate.eligibility_decisions)
        + len(aggregate.preference_sets)
        + len(aggregate.ranked_candidates)
    )
    assert _count("weekly_workforce_proposal_events") == 1


class _FailingEventRepository(SqlWeeklyWorkforceProposalEventRepository):
    def _append_event_with_connection(self, **kwargs):
        raise RuntimeError("forced event failure")


def test_event_failure_rolls_back_new_snapshot_proposal_and_all_children() -> None:
    snapshot, aggregate = _build_revision()
    uow = WeeklyWorkforceProposalUnitOfWork(
        event_repository=_FailingEventRepository()
    )

    with pytest.raises(RuntimeError, match="forced event failure"):
        _save_with_event(uow, snapshot, aggregate, _event(aggregate))

    for table in TABLES:
        assert _count(table) == 0


def test_preexisting_snapshot_survives_event_failure() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, first = _build_revision(
        snapshot_id="shared-snapshot",
        fingerprint="shared-fingerprint",
    )
    repository.save_revision(
        organization_id=snapshot.organization_id,
        snapshot=snapshot,
        aggregate=first,
    )
    second = first.model_copy(
        update={"proposal": first.proposal.model_copy(update={"version": 2})}
    )
    uow = WeeklyWorkforceProposalUnitOfWork(
        event_repository=_FailingEventRepository()
    )

    with pytest.raises(RuntimeError, match="forced event failure"):
        _save_with_event(uow, snapshot, second, _event(second))

    assert _count("weekly_planning_input_snapshots") == 1
    assert _count("weekly_workforce_proposals") == 1
    assert _count("weekly_workforce_proposal_events") == 0
    assert repository.get_revision(
        organization_id=snapshot.organization_id,
        proposal_id=first.proposal.proposal_id,
        version=1,
    ) == first


def test_proposal_failure_and_duplicate_revision_never_append_event() -> None:
    snapshot, aggregate = _build_revision()
    repository = SqlWeeklyWorkforceProposalRepository()
    repository.save_revision(
        organization_id=snapshot.organization_id,
        snapshot=snapshot,
        aggregate=aggregate,
    )

    with pytest.raises(WeeklyWorkforceProposalRevisionAlreadyExistsError):
        _save_with_event(
            WeeklyWorkforceProposalUnitOfWork(),
            snapshot,
            aggregate,
            _event(aggregate),
        )

    assert _count("weekly_workforce_proposal_events") == 0


def test_duplicate_event_inside_transaction_rolls_back_proposal_and_first_event() -> None:
    snapshot, aggregate = _build_revision()
    event = _event(aggregate)

    with pytest.raises(WeeklyWorkforceProposalEventAlreadyExistsError):
        with WeeklyWorkforceProposalUnitOfWork().transaction() as tx:
            tx.proposals.save_revision(
                organization_id=snapshot.organization_id,
                snapshot=snapshot,
                aggregate=aggregate,
            )
            tx.events.append_event(
                organization_id=snapshot.organization_id,
                event=event,
            )
            tx.events.append_event(
                organization_id=snapshot.organization_id,
                event=event,
            )

    for table in TABLES:
        assert _count(table) == 0


class _CapturingProposalRepository(SqlWeeklyWorkforceProposalRepository):
    connection_ids: list[int]

    def __init__(self) -> None:
        self.connection_ids = []

    def _save_revision_with_connection(self, *, conn, **kwargs):
        self.connection_ids.append(id(conn))
        return super()._save_revision_with_connection(conn=conn, **kwargs)


class _CapturingEventRepository(SqlWeeklyWorkforceProposalEventRepository):
    connection_ids: list[int]

    def __init__(self) -> None:
        self.connection_ids = []

    def _append_event_with_connection(self, *, conn, **kwargs):
        self.connection_ids.append(id(conn))
        return super()._append_event_with_connection(conn=conn, **kwargs)


def test_uow_uses_one_session_one_connection_and_one_commit(monkeypatch) -> None:
    counts = {"sessions": 0, "commits": 0, "rollbacks": 0}

    @contextmanager
    def counted_session():
        counts["sessions"] += 1
        conn = get_connection()
        try:
            yield conn
            conn.commit()
            counts["commits"] += 1
        except Exception:
            conn.rollback()
            counts["rollbacks"] += 1
            raise
        finally:
            conn.close()

    monkeypatch.setattr(uow_module, "db_session", counted_session)
    proposals = _CapturingProposalRepository()
    events = _CapturingEventRepository()
    snapshot, aggregate = _build_revision()

    _save_with_event(
        WeeklyWorkforceProposalUnitOfWork(
            proposal_repository=proposals,
            event_repository=events,
        ),
        snapshot,
        aggregate,
        _event(aggregate),
    )

    assert counts == {"sessions": 1, "commits": 1, "rollbacks": 0}
    assert proposals.connection_ids == events.connection_ids
    assert len(proposals.connection_ids) == 1


def test_uow_failure_uses_one_rollback_and_no_commit(monkeypatch) -> None:
    counts = {"sessions": 0, "commits": 0, "rollbacks": 0}

    @contextmanager
    def counted_session():
        counts["sessions"] += 1
        conn = get_connection()
        try:
            yield conn
            conn.commit()
            counts["commits"] += 1
        except Exception:
            conn.rollback()
            counts["rollbacks"] += 1
            raise
        finally:
            conn.close()

    monkeypatch.setattr(uow_module, "db_session", counted_session)
    snapshot, aggregate = _build_revision()
    uow = WeeklyWorkforceProposalUnitOfWork(
        event_repository=_FailingEventRepository()
    )

    with pytest.raises(RuntimeError, match="forced event failure"):
        _save_with_event(uow, snapshot, aggregate, _event(aggregate))

    assert counts == {"sessions": 1, "commits": 0, "rollbacks": 1}


def test_connection_bound_proposal_save_does_not_commit_itself() -> None:
    snapshot, aggregate = _build_revision()
    connection = get_connection()
    try:
        SqlWeeklyWorkforceProposalRepository()._save_revision_with_connection(
            conn=connection,
            organization_id=snapshot.organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )
        connection.rollback()
    finally:
        connection.close()

    for table in TABLES:
        assert _count(table) == 0

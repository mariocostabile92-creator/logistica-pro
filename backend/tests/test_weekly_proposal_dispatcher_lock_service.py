import json
from contextlib import contextmanager
from datetime import datetime, timezone
from inspect import getsource

import pytest

from app.core.database import db_session
from app.domain.workforce_auto_planning import (
    DispatcherAssignmentLockAssignmentNotFoundError,
    DispatcherAssignmentLockCommand,
    WeeklyWorkforceProposalRevisionNotFoundError,
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
from app.services.weekly_proposal_dispatcher_lock_service import (
    DISPATCHER_ASSIGNMENT_LOCKED_EVENT_TYPE,
    DISPATCHER_ASSIGNMENT_UNLOCKED_EVENT_TYPE,
    persist_dispatcher_assignment_lock,
)
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)
from app.services import weekly_proposal_dispatcher_lock_service as service_module
from tests.test_weekly_proposal_dispatcher_edit_service import (
    ORGANIZATION_ID,
    PROPOSAL_ID,
    TABLES,
    _scenario,
)


LOCKED_AT = datetime(2026, 8, 24, 9, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_proposal_tables() -> None:
    init_schema()
    with db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


def _target(aggregate):
    return aggregate.assignments[0]


def _with_target_locked(previous, locked: bool):
    target = _target(previous).model_copy(update={"locked": locked})
    return previous.model_copy(
        update={"assignments": (target, *previous.assignments[1:])}
    )


def _command(previous, *, locked: bool, assignment_id: str | None = None):
    return DispatcherAssignmentLockCommand(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        proposal_version=previous.proposal.version,
        assignment_id=assignment_id or _target(previous).assignment_id,
        locked=locked,
        actor_id="dispatcher-one",
        reason="Preserve dispatcher decision.",
        created_at=LOCKED_AT,
    )


class _EventIdFactory:
    def __init__(self, value: str = "event-lock-one") -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    def __call__(self, **values: object) -> str:
        self.calls.append(values)
        return self.value


def _persist_previous(snapshot, previous):
    repository = SqlWeeklyWorkforceProposalRepository()
    repository.save_revision(
        organization_id=ORGANIZATION_ID,
        snapshot=snapshot,
        aggregate=previous,
    )
    return repository


def _execute(repository, snapshot, command, *, uow=None, factory=None):
    selected_factory = factory if factory is not None else _EventIdFactory()
    persisted = persist_dispatcher_assignment_lock(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        previous_version=command.proposal_version,
        snapshot=snapshot,
        command=command,
        event_id_factory=selected_factory,
        repository=repository,
        unit_of_work=uow or WeeklyWorkforceProposalUnitOfWork(),
    )
    return persisted, selected_factory


def _event_row():
    with db_session() as conn:
        return conn.execute(
            "SELECT * FROM weekly_workforce_proposal_events"
        ).fetchone()


def _table_count(table: str) -> int:
    with db_session() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int(row["total"])


@pytest.mark.parametrize(
    ("initial_locked", "requested_locked", "expected_event_type"),
    (
        (False, True, DISPATCHER_ASSIGNMENT_LOCKED_EVENT_TYPE),
        (True, False, DISPATCHER_ASSIGNMENT_UNLOCKED_EVENT_TYPE),
        (True, True, DISPATCHER_ASSIGNMENT_LOCKED_EVENT_TYPE),
        (False, False, DISPATCHER_ASSIGNMENT_UNLOCKED_EVENT_TYPE),
    ),
)
def test_lock_unlock_and_idempotent_actions_persist_revision_and_event(
    initial_locked,
    requested_locked,
    expected_event_type,
) -> None:
    snapshot, generated_previous = _scenario()
    previous = _with_target_locked(generated_previous, initial_locked)
    repository = _persist_previous(snapshot, previous)
    command = _command(previous, locked=requested_locked)
    previous_before = previous.model_dump(mode="json")
    command_before = command.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")
    original_target = _target(previous)

    persisted, factory = _execute(repository, snapshot, command)

    loaded = repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=2,
    )
    updated = _target(persisted)
    row = _event_row()
    payload = json.loads(row["payload_json"])
    assert persisted == loaded
    assert persisted.proposal.version == 2
    assert persisted.proposal.proposal_id == PROPOSAL_ID
    assert updated.locked is requested_locked
    assert updated.model_dump(exclude={"locked"}) == original_target.model_dump(
        exclude={"locked"}
    )
    assert updated.origin == original_target.origin
    assert updated.status == original_target.status
    assert persisted.assignments[1:] == previous.assignments[1:]
    assert persisted.coverage_gaps == previous.coverage_gaps
    assert persisted.eligibility_decisions == previous.eligibility_decisions
    assert persisted.preference_sets == previous.preference_sets
    assert persisted.ranked_candidates == previous.ranked_candidates
    assert row["event_id"] == "event-lock-one"
    assert row["event_type"] == expected_event_type
    assert row["proposal_version"] == 2
    assert row["actor_id"] == "dispatcher-one"
    assert row["reason"] == "Preserve dispatcher decision."
    assert row["created_at"] == LOCKED_AT.isoformat()
    assert payload == {
        "actor_id": "dispatcher-one",
        "assignment_id": command.assignment_id,
        "locked": requested_locked,
        "new_version": 2,
        "previous_version": 1,
        "reason": "Preserve dispatcher decision.",
    }
    assert len(factory.calls) == 1
    assert factory.calls[0]["assignment_id"] == command.assignment_id
    assert factory.calls[0]["event_type"] == expected_event_type
    assert previous.model_dump(mode="json") == previous_before
    assert command.model_dump(mode="json") == command_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=1,
    ) == previous


class _FailIfTransactionStarts(WeeklyWorkforceProposalUnitOfWork):
    @contextmanager
    def transaction(self):
        raise AssertionError("transaction must not start")
        yield


def test_stale_stops_before_c5d_factory_and_transaction(monkeypatch) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    second = previous.model_copy(
        update={"proposal": previous.proposal.model_copy(update={"version": 2})}
    )
    repository.save_revision(
        organization_id=ORGANIZATION_ID,
        snapshot=snapshot,
        aggregate=second,
    )
    factory = _EventIdFactory()

    def fail_lock(**kwargs):
        raise AssertionError("C5D must not run")

    monkeypatch.setattr(
        service_module,
        "apply_dispatcher_assignment_lock",
        fail_lock,
    )
    with pytest.raises(WeeklyProposalRegenerationStaleRevisionError):
        _execute(
            repository,
            snapshot,
            _command(previous, locked=True),
            uow=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_row() is None
    assert len(repository.list_revisions(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
    )) == 2


def test_c5d_error_propagates_without_event_or_revision() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    factory = _EventIdFactory()

    with pytest.raises(DispatcherAssignmentLockAssignmentNotFoundError):
        _execute(
            repository,
            snapshot,
            _command(previous, locked=True, assignment_id="missing-assignment"),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_row() is None
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id=ORGANIZATION_ID,
            proposal_id=PROPOSAL_ID,
            version=2,
        )


class _FailingEventRepository(SqlWeeklyWorkforceProposalEventRepository):
    def _append_event_with_connection(self, **kwargs):
        raise RuntimeError("forced event failure")


class _DuplicateEventRepository(SqlWeeklyWorkforceProposalEventRepository):
    def _append_event_with_connection(self, **kwargs):
        event = super()._append_event_with_connection(**kwargs)
        super()._append_event_with_connection(**kwargs)
        return event


@pytest.mark.parametrize(
    "event_repository",
    (_FailingEventRepository(), _DuplicateEventRepository()),
)
def test_event_failure_or_duplicate_rolls_back_new_revision(event_repository) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    before_counts = {
        table: _table_count(table)
        for table in TABLES
        if table != "weekly_workforce_proposal_events"
    }

    with pytest.raises(RuntimeError):
        _execute(
            repository,
            snapshot,
            _command(previous, locked=True),
            uow=WeeklyWorkforceProposalUnitOfWork(
                event_repository=event_repository
            ),
        )

    assert _event_row() is None
    assert {
        table: _table_count(table)
        for table in before_counts
    } == before_counts
    assert repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=1,
    ) == previous
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id=ORGANIZATION_ID,
            proposal_id=PROPOSAL_ID,
            version=2,
        )


class _FailingProposalRepository(SqlWeeklyWorkforceProposalRepository):
    def _save_revision_with_connection(self, **kwargs):
        raise RuntimeError("forced proposal failure")


class _CapturingEventRepository(SqlWeeklyWorkforceProposalEventRepository):
    def __init__(self) -> None:
        self.calls = 0
        self.connection_ids: list[int] = []

    def _append_event_with_connection(self, *, conn, **kwargs):
        self.calls += 1
        self.connection_ids.append(id(conn))
        return super()._append_event_with_connection(conn=conn, **kwargs)


class _CapturingProposalRepository(SqlWeeklyWorkforceProposalRepository):
    def __init__(self) -> None:
        self.connection_ids: list[int] = []

    def _save_revision_with_connection(self, *, conn, **kwargs):
        self.connection_ids.append(id(conn))
        return super()._save_revision_with_connection(conn=conn, **kwargs)


def test_proposal_failure_never_appends_event() -> None:
    snapshot, previous = _scenario()
    read_repository = _persist_previous(snapshot, previous)
    events = _CapturingEventRepository()

    with pytest.raises(RuntimeError, match="forced proposal failure"):
        _execute(
            read_repository,
            snapshot,
            _command(previous, locked=True),
            uow=WeeklyWorkforceProposalUnitOfWork(
                proposal_repository=_FailingProposalRepository(),
                event_repository=events,
            ),
        )

    assert events.calls == 0
    assert _event_row() is None


def test_proposal_and_event_use_same_connection() -> None:
    snapshot, previous = _scenario()
    read_repository = _persist_previous(snapshot, previous)
    proposals = _CapturingProposalRepository()
    events = _CapturingEventRepository()

    _execute(
        read_repository,
        snapshot,
        _command(previous, locked=True),
        uow=WeeklyWorkforceProposalUnitOfWork(
            proposal_repository=proposals,
            event_repository=events,
        ),
    )

    assert proposals.connection_ids == events.connection_ids
    assert len(proposals.connection_ids) == 1
    assert events.calls == 1


class _FakeReadRepository:
    def __init__(self, previous) -> None:
        self.previous = previous

    def get_revision(self, **kwargs):
        return self.previous

    def latest_revision(self, **kwargs):
        return self.previous


def test_new_snapshot_is_rolled_back_when_event_fails() -> None:
    snapshot, previous = _scenario()

    with pytest.raises(RuntimeError, match="forced event failure"):
        _execute(
            _FakeReadRepository(previous),
            snapshot,
            _command(previous, locked=True),
            uow=WeeklyWorkforceProposalUnitOfWork(
                event_repository=_FailingEventRepository()
            ),
        )

    for table in TABLES:
        assert _table_count(table) == 0


def test_service_contains_no_forbidden_lifecycle_or_runtime_workflows() -> None:
    source = getsource(service_module).casefold()

    assert "superseded" not in source
    assert "current_organization_id" not in source
    assert "approve" not in source
    assert "publish" not in source
    assert "regenerate_weekly" not in source
    assert "fastapi" not in source

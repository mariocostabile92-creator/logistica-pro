import json
from contextlib import contextmanager
from datetime import datetime, timezone
from inspect import getsource

import pytest

from app.core.database import db_session
from app.domain.workforce_auto_planning import (
    CoverageGap,
    ProposedShiftAssignmentOrigin,
    WeeklyProposalStatusTransitionCommand,
    WeeklyProposalStatusTransitionNotAllowedError,
    WeeklyProposalStatusTransitionScopeMismatchError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalSnapshotMismatchError,
    WeeklyWorkforceProposalStatus,
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
from app.services import weekly_proposal_status_transition_service as service_module
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)
from app.services.weekly_proposal_status_transition_service import (
    WEEKLY_PROPOSAL_APPROVED_EVENT_TYPE,
    WEEKLY_PROPOSAL_UNDER_REVIEW_EVENT_TYPE,
    persist_weekly_proposal_status_transition,
)
from tests.test_weekly_proposal_dispatcher_edit_service import (
    ORGANIZATION_ID,
    PROPOSAL_ID,
    TABLES,
    _scenario,
)


REVIEWED_AT = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)
APPROVED_AT = datetime(2026, 8, 25, 11, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_proposal_tables() -> None:
    init_schema()
    with db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


class _EventIdFactory:
    def __init__(self, value: str = "event-status-one") -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    def __call__(self, **values: object) -> str:
        self.calls.append(values)
        return self.value


class _FailIfTransactionStarts(WeeklyWorkforceProposalUnitOfWork):
    @contextmanager
    def transaction(self):
        raise AssertionError("transaction must not start")
        yield


def _command(
    previous,
    target_status: WeeklyWorkforceProposalStatus,
    **updates: object,
) -> WeeklyProposalStatusTransitionCommand:
    values: dict[str, object] = {
        "organization_id": ORGANIZATION_ID,
        "proposal_id": PROPOSAL_ID,
        "proposal_version": previous.proposal.version,
        "target_status": target_status,
        "actor_id": "dispatcher-one",
        "reason": "Operational review completed.",
        "created_at": (
            APPROVED_AT
            if target_status is WeeklyWorkforceProposalStatus.APPROVED
            else REVIEWED_AT
        ),
    }
    values.update(updates)
    return WeeklyProposalStatusTransitionCommand(**values)


def _persist_previous(snapshot, previous):
    repository = SqlWeeklyWorkforceProposalRepository()
    repository.save_revision(
        organization_id=ORGANIZATION_ID,
        snapshot=snapshot,
        aggregate=previous,
    )
    return repository


def _execute(
    repository,
    snapshot,
    command,
    *,
    previous_version=None,
    unit_of_work=None,
    factory=None,
):
    selected_factory = factory or _EventIdFactory()
    persisted = persist_weekly_proposal_status_transition(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        previous_version=(
            command.proposal_version
            if previous_version is None
            else previous_version
        ),
        snapshot=snapshot,
        command=command,
        event_id_factory=selected_factory,
        repository=repository,
        unit_of_work=unit_of_work or WeeklyWorkforceProposalUnitOfWork(),
    )
    return persisted, selected_factory


def _event_rows():
    with db_session() as conn:
        return conn.execute(
            """
            SELECT * FROM weekly_workforce_proposal_events
            ORDER BY proposal_version, event_id
            """
        ).fetchall()


def _table_count(table: str) -> int:
    with db_session() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int(row["total"])


def _review(snapshot, previous, repository):
    return _execute(
        repository,
        snapshot,
        _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
        factory=_EventIdFactory("event-under-review"),
    )[0]


def test_generated_to_under_review_persists_revision_and_audit_event() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW)
    factory = _EventIdFactory("event-under-review")
    previous_before = previous.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")
    command_before = command.model_dump(mode="json")

    persisted, _ = _execute(
        repository,
        snapshot,
        command,
        factory=factory,
    )

    loaded = repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=2,
    )
    row = _event_rows()[0]
    payload = json.loads(row["payload_json"])
    assert persisted == loaded
    assert persisted.proposal.status is WeeklyWorkforceProposalStatus.UNDER_REVIEW
    assert persisted.proposal.version == 2
    assert row["event_id"] == "event-under-review"
    assert row["event_type"] == WEEKLY_PROPOSAL_UNDER_REVIEW_EVENT_TYPE
    assert row["proposal_version"] == 2
    assert row["actor_id"] == command.actor_id
    assert row["reason"] == command.reason
    assert row["created_at"] == command.created_at.isoformat()
    assert payload == {
        "actor_id": command.actor_id,
        "input_fingerprint": previous.proposal.input_fingerprint,
        "input_snapshot_id": previous.proposal.input_snapshot_id,
        "new_version": 2,
        "previous_status": "GENERATED",
        "previous_version": 1,
        "reason": command.reason,
        "target_status": "UNDER_REVIEW",
    }
    assert factory.calls == [
        {
            "organization_id": ORGANIZATION_ID,
            "proposal_id": PROPOSAL_ID,
            "proposal_version": 2,
            "event_type": WEEKLY_PROPOSAL_UNDER_REVIEW_EVENT_TYPE,
            "previous_status": WeeklyWorkforceProposalStatus.GENERATED,
            "target_status": WeeklyWorkforceProposalStatus.UNDER_REVIEW,
        }
    ]
    assert previous.model_dump(mode="json") == previous_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert command.model_dump(mode="json") == command_before


def test_under_review_to_approved_persists_revision_and_approved_event() -> None:
    snapshot, generated = _scenario()
    repository = _persist_previous(snapshot, generated)
    under_review = _review(snapshot, generated, repository)
    command = _command(under_review, WeeklyWorkforceProposalStatus.APPROVED)
    factory = _EventIdFactory("event-approved")

    persisted, _ = _execute(repository, snapshot, command, factory=factory)

    rows = _event_rows()
    assert persisted.proposal.status is WeeklyWorkforceProposalStatus.APPROVED
    assert persisted.proposal.version == 3
    assert rows[-1]["event_id"] == "event-approved"
    assert rows[-1]["event_type"] == WEEKLY_PROPOSAL_APPROVED_EVENT_TYPE
    assert rows[-1]["proposal_version"] == 3
    assert json.loads(rows[-1]["payload_json"])["previous_status"] == (
        "UNDER_REVIEW"
    )
    assert json.loads(rows[-1]["payload_json"])["target_status"] == "APPROVED"


def test_approval_allows_gap_manual_violation_and_locked_manual_assignment() -> None:
    snapshot, generated = _scenario()
    existing_gap = generated.coverage_gaps[0]
    positive_gap = CoverageGap.model_validate(
        {
            **existing_gap.model_dump(),
            "required_quantity": 2,
            "proposed_quantity": 1,
            "gap_quantity": 1,
        }
    )
    locked_manual = generated.assignments[0].model_copy(
        update={
            "origin": ProposedShiftAssignmentOrigin.MANUAL,
            "locked": True,
        }
    )
    generated = generated.model_copy(
        update={
            "assignments": (locked_manual, *generated.assignments[1:]),
            "coverage_gaps": (positive_gap, *generated.coverage_gaps[1:]),
        }
    )
    assert any(
        not evaluation.passed
        for decision in generated.eligibility_decisions
        for evaluation in decision.evaluations
    )
    repository = _persist_previous(snapshot, generated)
    under_review = _review(snapshot, generated, repository)

    approved, _ = _execute(
        repository,
        snapshot,
        _command(under_review, WeeklyWorkforceProposalStatus.APPROVED),
        factory=_EventIdFactory("event-approved"),
    )

    assert approved.proposal.status is WeeklyWorkforceProposalStatus.APPROVED
    assert approved.coverage_gaps[0].gap_quantity == 1
    assert approved.assignments[0].origin is ProposedShiftAssignmentOrigin.MANUAL
    assert approved.assignments[0].locked is True
    assert approved.assignments == under_review.assignments
    assert approved.eligibility_decisions == under_review.eligibility_decisions


@pytest.mark.parametrize(
    "target",
    (
        WeeklyWorkforceProposalStatus.APPROVED,
        WeeklyWorkforceProposalStatus.GENERATED,
    ),
)
def test_invalid_transition_stops_before_factory_and_transaction(target) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    factory = _EventIdFactory()

    with pytest.raises(WeeklyProposalStatusTransitionNotAllowedError):
        _execute(
            repository,
            snapshot,
            _command(previous, target),
            unit_of_work=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_rows() == []


def test_approved_to_under_review_is_rejected_before_factory_and_transaction() -> None:
    snapshot, generated = _scenario()
    repository = _persist_previous(snapshot, generated)
    under_review = _review(snapshot, generated, repository)
    approved, _ = _execute(
        repository,
        snapshot,
        _command(under_review, WeeklyWorkforceProposalStatus.APPROVED),
        factory=_EventIdFactory("event-approved"),
    )
    factory = _EventIdFactory("event-invalid")

    with pytest.raises(WeeklyProposalStatusTransitionNotAllowedError):
        _execute(
            repository,
            snapshot,
            _command(approved, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
            unit_of_work=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert len(_event_rows()) == 2


@pytest.mark.parametrize(
    "updates",
    (
        {"organization_id": "organization-two"},
        {"proposal_id": "proposal-two"},
        {"proposal_version": 99},
    ),
)
def test_command_scope_mismatch_stops_before_factory_and_transaction(updates) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    factory = _EventIdFactory()

    with pytest.raises(WeeklyProposalStatusTransitionScopeMismatchError):
        _execute(
            repository,
            snapshot,
            _command(
                previous,
                WeeklyWorkforceProposalStatus.UNDER_REVIEW,
                **updates,
            ),
            previous_version=previous.proposal.version,
            unit_of_work=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_rows() == []


def test_stale_revision_stops_before_transition_factory_and_transaction(
    monkeypatch,
) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    revision_two = previous.model_copy(
        update={"proposal": previous.proposal.model_copy(update={"version": 2})}
    )
    repository.save_revision(
        organization_id=ORGANIZATION_ID,
        snapshot=snapshot,
        aggregate=revision_two,
    )
    factory = _EventIdFactory()

    def fail_transition(**kwargs):
        raise AssertionError("C8A must not run for stale revision")

    monkeypatch.setattr(
        service_module,
        "apply_weekly_proposal_status_transition",
        fail_transition,
    )
    with pytest.raises(WeeklyProposalRegenerationStaleRevisionError):
        _execute(
            repository,
            snapshot,
            _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
            unit_of_work=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_rows() == []


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
def test_event_failure_or_duplicate_rolls_back_proposal(event_repository) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    before_counts = {table: _table_count(table) for table in TABLES}

    with pytest.raises(RuntimeError):
        _execute(
            repository,
            snapshot,
            _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
            unit_of_work=WeeklyWorkforceProposalUnitOfWork(
                event_repository=event_repository
            ),
        )

    assert {table: _table_count(table) for table in TABLES} == before_counts
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
    repository = _persist_previous(snapshot, previous)
    events = _CapturingEventRepository()

    with pytest.raises(RuntimeError, match="forced proposal failure"):
        _execute(
            repository,
            snapshot,
            _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
            unit_of_work=WeeklyWorkforceProposalUnitOfWork(
                proposal_repository=_FailingProposalRepository(),
                event_repository=events,
            ),
        )

    assert events.calls == 0
    assert _event_rows() == []


def test_snapshot_mismatch_rolls_back_without_event() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    mismatched_snapshot = snapshot.model_copy(
        update={"fingerprint": "different-fingerprint"}
    )

    with pytest.raises(WeeklyWorkforceProposalSnapshotMismatchError):
        _execute(
            repository,
            mismatched_snapshot,
            _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
        )

    assert _event_rows() == []
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id=ORGANIZATION_ID,
            proposal_id=PROPOSAL_ID,
            version=2,
        )


def test_proposal_and_event_share_one_connection() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    proposals = _CapturingProposalRepository()
    events = _CapturingEventRepository()

    _execute(
        repository,
        snapshot,
        _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
        unit_of_work=WeeklyWorkforceProposalUnitOfWork(
            proposal_repository=proposals,
            event_repository=events,
        ),
    )

    assert proposals.connection_ids == events.connection_ids
    assert len(proposals.connection_ids) == 1


def test_status_transition_preserves_all_operational_content_and_snapshot() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    snapshot_row_before = None
    with db_session() as conn:
        snapshot_row_before = dict(
            conn.execute(
                "SELECT * FROM weekly_planning_input_snapshots"
            ).fetchone()
        )

    persisted, _ = _execute(
        repository,
        snapshot,
        _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
    )

    with db_session() as conn:
        snapshot_rows = conn.execute(
            "SELECT * FROM weekly_planning_input_snapshots"
        ).fetchall()
    assert len(snapshot_rows) == 1
    assert dict(snapshot_rows[0]) == snapshot_row_before
    assert persisted.assignments == previous.assignments
    assert persisted.coverage_gaps == previous.coverage_gaps
    assert persisted.eligibility_decisions == previous.eligibility_decisions
    assert persisted.preference_sets == previous.preference_sets
    assert persisted.ranked_candidates == previous.ranked_candidates
    assert tuple(item.locked for item in persisted.assignments) == tuple(
        item.locked for item in previous.assignments
    )
    assert repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=1,
    ) == previous


def test_service_boundary_is_status_and_event_persistence_only() -> None:
    source = getsource(service_module).lower()

    for forbidden in (
        "driver_shift_planning",
        "published_row",
        "workforce_day_status",
        "vehicle_assignment",
        "supersede",
        "currentness",
        "readiness",
        "fastapi",
    ):
        assert forbidden not in source

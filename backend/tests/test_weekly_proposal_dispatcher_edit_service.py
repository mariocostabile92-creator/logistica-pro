import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource

import pytest

from app.core.database import db_session
from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    CurrentMemberContractStateSnapshot,
    DispatcherManualOverride,
    DispatcherManualOverrideCandidateNotFoundError,
    DispatcherOverrideOperationType,
    DispatcherWeeklyEditCommand,
    OperationalDemand,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
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
from app.services.weekly_proposal_dispatcher_edit_service import (
    DISPATCHER_MANUAL_EDIT_EVENT_TYPE,
    persist_dispatcher_weekly_edit,
)
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)
from app.services import weekly_proposal_dispatcher_edit_service as service_module


ORGANIZATION_ID = "organization-one"
PROPOSAL_ID = "proposal-one"
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
WINDOW_ONE = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
WINDOW_TWO = TimeWindow(
    external_identifier="window-two",
    starts_at="13:00",
    ends_at="17:00",
)
CAPABILITY = "opaque-capability"
CREATED_AT = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)
EDITED_AT = datetime(2026, 8, 24, 6, tzinfo=timezone.utc)
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)
TABLES = (
    "weekly_workforce_proposal_events",
    "weekly_workforce_proposal_explainability",
    "weekly_workforce_proposal_gaps",
    "weekly_workforce_proposal_assignments",
    "weekly_workforce_proposals",
    "weekly_planning_input_snapshots",
)


@pytest.fixture(autouse=True)
def reset_proposal_tables() -> None:
    init_schema()
    with db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


def _candidate(identifier: str, *, callable_value: bool) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=identifier,
            display_name=identifier,
            capabilities=(CAPABILITY,),
        ),
        availability=tuple(
            WorkforceCandidateAvailabilitySnapshot(
                date=operational_date,
                availability=ResourceAvailability(
                    resource_identifier=identifier,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=callable_value,
                    observed_state=(
                        "available" if callable_value else "unavailable"
                    ),
                ),
            )
            for operational_date in (DAY_ONE, DAY_TWO)
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            weekly_hours=Decimal("40")
        ),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("0"),
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _scenario():
    demands = tuple(
        OperationalDemand(
            organization_id=ORGANIZATION_ID,
            operational_unit=UNIT,
            date=operational_date,
            time_window=time_window,
            capability_or_workload=CAPABILITY,
            base_quantity=1,
            target_quantity=1,
            source="normalized-source",
            applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
        )
        for operational_date, time_window in (
            (DAY_ONE, WINDOW_ONE),
            (DAY_TWO, WINDOW_TWO),
        )
    )
    snapshot = WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-one",
        organization_id=ORGANIZATION_ID,
        period_start=DAY_ONE,
        period_end=DAY_TWO,
        operational_unit=UNIT,
        demands=demands,
        workforce_candidates=(
            _candidate("member-a", callable_value=True),
            _candidate("member-z", callable_value=False),
        ),
        policy_set_identifier="policy-set",
        policy_set_version="1",
        created_at=CREATED_AT,
        fingerprint="fingerprint-one",
    )

    def assignment_id_factory(**values: object) -> str:
        return f"assignment:{values['operational_date'].isoformat()}"

    generated = generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=assignment_id_factory,
    )
    previous = compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=generated,
        proposal_id=PROPOSAL_ID,
        version=1,
        created_at=CREATED_AT,
    )
    return snapshot, previous


def _caller_violation() -> ConstraintEvaluation:
    return ConstraintEvaluation(
        code="caller-false-violation",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=False,
        message="Caller values are not authoritative.",
        rule_origin="caller",
    )


def _command(
    operation: DispatcherOverrideOperationType,
    previous,
    *,
    blocked_replacement: bool = False,
    caller_violations: tuple[ConstraintEvaluation, ...] = (),
) -> DispatcherWeeklyEditCommand:
    target, destination = previous.assignments
    assignment_id = (
        None
        if operation == DispatcherOverrideOperationType.ADD_ASSIGNMENT
        else target.assignment_id
    )
    replacement = None
    if operation != DispatcherOverrideOperationType.REMOVE_ASSIGNMENT:
        updates: dict[str, object] = {
            "origin": ProposedShiftAssignmentOrigin.MANUAL,
            "status": ProposedShiftAssignmentStatus.PROPOSED,
        }
        if operation == DispatcherOverrideOperationType.ADD_ASSIGNMENT:
            updates["assignment_id"] = "assignment-added"
        elif operation == DispatcherOverrideOperationType.REPLACE_ASSIGNMENT:
            updates["assignment_id"] = "assignment-replacement"
        elif operation == DispatcherOverrideOperationType.MOVE_ASSIGNMENT:
            updates.update(
                {
                    "date": destination.date,
                    "time_window": destination.time_window,
                    "demand_trace_id": destination.demand_trace_id,
                }
            )
        elif operation == DispatcherOverrideOperationType.MODIFY_ASSIGNMENT:
            updates["shift_identifier"] = "dispatcher-shift"
        if blocked_replacement:
            updates["workforce_member_id"] = "member-z"
        replacement = target.model_copy(update=updates)

    override = DispatcherManualOverride(
        override_id=f"override-{operation.value.lower()}",
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        proposal_version=1,
        assignment_id=assignment_id,
        operation_type=operation,
        reason="Dispatcher operational correction.",
        actor_id="dispatcher-one",
        violations=caller_violations,
        created_at=EDITED_AT,
    )
    return DispatcherWeeklyEditCommand(
        override=override,
        replacement_assignment=replacement,
        created_at=EDITED_AT,
    )


class _EventIdFactory:
    def __init__(self, value: str = "event-one") -> None:
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
    result = persist_dispatcher_weekly_edit(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        previous_version=1,
        snapshot=snapshot,
        command=command,
        capability_mappings=MAPPINGS,
        event_id_factory=selected_factory,
        repository=repository,
        unit_of_work=uow or WeeklyWorkforceProposalUnitOfWork(),
    )
    return result, selected_factory


def _event_row():
    with db_session() as conn:
        return conn.execute(
            "SELECT * FROM weekly_workforce_proposal_events"
        ).fetchone()


@pytest.mark.parametrize("operation", tuple(DispatcherOverrideOperationType))
def test_all_edit_operations_persist_new_revision_and_audit_event(operation) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(operation, previous)
    previous_before = previous.model_dump(mode="json")
    command_before = command.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")

    persisted, factory = _execute(repository, snapshot, command)

    loaded = repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=2,
    )
    row = _event_row()
    payload = json.loads(row["payload_json"])
    assert persisted == loaded
    assert persisted.proposal.version == 2
    assert persisted.proposal.proposal_id == PROPOSAL_ID
    assert row["event_type"] == DISPATCHER_MANUAL_EDIT_EVENT_TYPE
    assert row["event_id"] == "event-one"
    assert row["proposal_version"] == 2
    assert row["actor_id"] == "dispatcher-one"
    assert row["reason"] == "Dispatcher operational correction."
    assert row["created_at"] == EDITED_AT.isoformat()
    assert payload["override_id"] == command.override.override_id
    assert payload["operation_type"] == operation.value
    assert payload["previous_version"] == 1
    assert payload["new_version"] == 2
    assert payload["target_assignment_id"] == command.override.assignment_id
    assert payload["replacement_assignment_id"] == (
        command.replacement_assignment.assignment_id
        if command.replacement_assignment is not None
        else None
    )
    assert len(factory.calls) == 1
    assert factory.calls[0]["proposal_version"] == 2
    assert previous.model_dump(mode="json") == previous_before
    assert command.model_dump(mode="json") == command_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=1,
    ) == previous


def test_revalidation_replaces_caller_violations_and_preserves_real_failure() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(
        DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        previous,
        blocked_replacement=True,
        caller_violations=(_caller_violation(),),
    )

    persisted, _ = _execute(repository, snapshot, command)

    payload = json.loads(_event_row()["payload_json"])
    assert persisted.proposal.version == 2
    assert [item["code"] for item in payload["violations"]] == [
        "daily-callability"
    ]
    assert "caller-false-violation" not in _event_row()["payload_json"]


def test_remove_clears_caller_violations_in_event_payload() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(
        DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
        previous,
        caller_violations=(_caller_violation(),),
    )

    _execute(repository, snapshot, command)

    assert json.loads(_event_row()["payload_json"])["violations"] == []


def test_structural_revalidation_failure_has_no_revision_event_or_event_id() -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(
        DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        previous,
    )
    command = command.model_copy(
        update={
            "replacement_assignment": command.replacement_assignment.model_copy(
                update={"workforce_member_id": "unknown-member"}
            )
        }
    )
    factory = _EventIdFactory()

    with pytest.raises(DispatcherManualOverrideCandidateNotFoundError):
        _execute(repository, snapshot, command, factory=factory)

    assert factory.calls == []
    assert _event_row() is None
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id=ORGANIZATION_ID,
            proposal_id=PROPOSAL_ID,
            version=2,
        )


class _FailIfTransactionStarts(WeeklyWorkforceProposalUnitOfWork):
    @contextmanager
    def transaction(self):
        raise AssertionError("transaction must not start")
        yield


def test_stale_revision_stops_before_factory_revalidation_and_transaction(
    monkeypatch,
) -> None:
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
    command = _command(
        DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        previous,
    )
    factory = _EventIdFactory()

    def fail_revalidation(**kwargs):
        raise AssertionError("revalidation must not run")

    monkeypatch.setattr(
        service_module,
        "revalidate_dispatcher_manual_override",
        fail_revalidation,
    )

    with pytest.raises(WeeklyProposalRegenerationStaleRevisionError):
        _execute(
            repository,
            snapshot,
            command,
            uow=_FailIfTransactionStarts(),
            factory=factory,
        )

    assert factory.calls == []
    assert _event_row() is None
    assert len(repository.list_revisions(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
    )) == 2


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
def test_event_failure_or_duplicate_rolls_back_complete_new_revision(
    event_repository,
) -> None:
    snapshot, previous = _scenario()
    repository = _persist_previous(snapshot, previous)
    command = _command(
        DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        previous,
    )
    previous_counts = {
        table: _table_count(table)
        for table in TABLES
        if table != "weekly_workforce_proposal_events"
    }

    with pytest.raises(RuntimeError):
        _execute(
            repository,
            snapshot,
            command,
            uow=WeeklyWorkforceProposalUnitOfWork(
                event_repository=event_repository
            ),
        )

    assert _event_row() is None
    assert {
        table: _table_count(table)
        for table in previous_counts
    } == previous_counts
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
            _command(DispatcherOverrideOperationType.ADD_ASSIGNMENT, previous),
            uow=WeeklyWorkforceProposalUnitOfWork(
                proposal_repository=_FailingProposalRepository(),
                event_repository=events,
            ),
        )

    assert events.calls == 0
    assert _event_row() is None


def test_service_writes_once_with_same_connection_for_proposal_and_event() -> None:
    snapshot, previous = _scenario()
    read_repository = _persist_previous(snapshot, previous)
    proposals = _CapturingProposalRepository()
    events = _CapturingEventRepository()

    _execute(
        read_repository,
        snapshot,
        _command(DispatcherOverrideOperationType.ADD_ASSIGNMENT, previous),
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
            _command(DispatcherOverrideOperationType.ADD_ASSIGNMENT, previous),
            uow=WeeklyWorkforceProposalUnitOfWork(
                event_repository=_FailingEventRepository()
            ),
        )

    for table in TABLES:
        assert _table_count(table) == 0


def _table_count(table: str) -> int:
    with db_session() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int(row["total"])


def test_service_has_no_forbidden_workflows_or_provider_queries() -> None:
    source = getsource(service_module).casefold()

    assert "current_organization_id" not in source
    assert "superseded" not in source
    assert "approve" not in source
    assert "publish" not in source
    assert "workforcecandidate" not in source
    assert "coverage" not in source
    assert "configuration" not in source
    assert "lock" not in source

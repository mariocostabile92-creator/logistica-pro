import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource

import pytest

from app.core.database import db_session as real_db_session
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
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposalOrganizationMismatchError,
    WeeklyWorkforceProposalRepository,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalSnapshotMismatchError,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
)
from app.repositories.weekly_workforce_proposal_repository import (
    SqlWeeklyWorkforceProposalRepository,
)
from app.repositories import weekly_workforce_proposal_repository as repo_module
from app.repositories.weekly_workforce_proposal_schema import init_schema


TABLES = (
    "weekly_workforce_proposal_events",
    "weekly_workforce_proposal_explainability",
    "weekly_workforce_proposal_gaps",
    "weekly_workforce_proposal_assignments",
    "weekly_workforce_proposals",
    "weekly_planning_input_snapshots",
)
OPERATION_DATE = date(2026, 8, 24)
CREATED_AT = datetime(2026, 8, 21, 10, tzinfo=timezone.utc)
CAPABILITY = "opaque-capability"


@pytest.fixture(autouse=True)
def reset_repository_tables() -> None:
    init_schema()
    with real_db_session() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")


def _unit(organization_id: str) -> OperationalUnit:
    return OperationalUnit(
        external_identifier=f"unit-{organization_id}",
        name=f"Unit {organization_id}",
    )


def _candidate(
    organization_id: str,
    member_id: str,
    *,
    assigned_minutes: Decimal,
) -> WorkforceCandidateSnapshot:
    unit = _unit(organization_id)
    return WorkforceCandidateSnapshot(
        organization_id=organization_id,
        human_resource=HumanResource(
            external_identifier=member_id,
            display_name=f"Driver {member_id}",
            capabilities=(CAPABILITY,),
        ),
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=OPERATION_DATE,
                availability=ResourceAvailability(
                    resource_identifier=member_id,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="available",
                    reason="Authoritative readiness.",
                    origin="workforce",
                ),
            ),
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            employment_type="generic-employment",
            weekly_hours=Decimal("40"),
            is_reserve=False,
        ),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=unit,
            candidate_unit=unit,
        ),
        recent_consecutivity=1,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=assigned_minutes,
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _build_revision(
    *,
    organization_id: str = "organization-one",
    proposal_id: str = "proposal-one",
    version: int = 1,
    snapshot_id: str | None = None,
    fingerprint: str | None = None,
    status: WeeklyWorkforceProposalStatus = WeeklyWorkforceProposalStatus.GENERATED,
):
    unit = _unit(organization_id)
    window = TimeWindow(
        external_identifier="window-morning",
        starts_at="08:00",
        ends_at="12:00",
    )
    demand = OperationalDemand(
        organization_id=organization_id,
        operational_unit=unit,
        date=OPERATION_DATE,
        time_window=window,
        capability_or_workload=CAPABILITY,
        base_quantity=1,
        target_quantity=1,
        source="normalized-source",
        applied_policy=AppliedPolicyMetadata(
            identifier="policy-rule",
            version="1",
            metadata=("rounding=deterministic",),
        ),
    )
    actual_snapshot_id = snapshot_id or f"snapshot-{organization_id}-{version}"
    actual_fingerprint = fingerprint or f"fingerprint-{organization_id}-{version}"
    snapshot = WeeklyPlanningInputSnapshot(
        snapshot_id=actual_snapshot_id,
        organization_id=organization_id,
        period_start=OPERATION_DATE,
        period_end=OPERATION_DATE,
        operational_unit=unit,
        demands=(demand,),
        workforce_candidates=(
            _candidate(
                organization_id,
                f"member-{organization_id}-a",
                assigned_minutes=Decimal("0"),
            ),
            _candidate(
                organization_id,
                f"member-{organization_id}-b",
                assigned_minutes=Decimal("60"),
            ),
        ),
        policy_set_identifier="policy-set",
        policy_set_version="1",
        created_at=datetime(2026, 8, 20, 9, tzinfo=timezone.utc),
        fingerprint=actual_fingerprint,
    )

    def assignment_id_factory(**values: object) -> str:
        return (
            f"assignment:{values['operational_date'].isoformat()}:"
            f"{values['workforce_member_id']}"
        )

    generated = generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=(
            WorkloadCapabilityMapping(
                workload_identifier=CAPABILITY,
                required_capabilities=(CAPABILITY,),
            ),
        ),
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=assignment_id_factory,
    )
    aggregate = compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=generated,
        proposal_id=proposal_id,
        version=version,
        created_at=CREATED_AT,
    )
    if status is not WeeklyWorkforceProposalStatus.GENERATED:
        aggregate = aggregate.model_copy(
            update={
                "proposal": aggregate.proposal.model_copy(
                    update={"status": status}
                )
            }
        )
    return snapshot, aggregate


def _save(
    repository: SqlWeeklyWorkforceProposalRepository,
    snapshot: WeeklyPlanningInputSnapshot,
    aggregate,
):
    return repository.save_revision(
        organization_id=snapshot.organization_id,
        snapshot=snapshot,
        aggregate=aggregate,
    )


def _table_count(table: str) -> int:
    with real_db_session() as conn:
        return int(conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"])


def test_protocol_is_implemented_and_save_get_round_trip_is_complete() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    assert isinstance(repository, WeeklyWorkforceProposalRepository)
    snapshot, aggregate = _build_revision()
    snapshot_before = snapshot.model_dump(mode="json")
    aggregate_before = aggregate.model_dump(mode="json")

    saved = _save(repository, snapshot, aggregate)
    loaded = repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assert saved is aggregate
    assert loaded == aggregate
    assert loaded.model_dump(mode="json") == aggregate_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert aggregate.model_dump(mode="json") == aggregate_before


def test_snapshot_payload_is_canonical_complete_and_reused_immutably() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, first = _build_revision(
        snapshot_id="shared-snapshot",
        fingerprint="shared-fingerprint",
    )
    _save(repository, snapshot, first)
    second = first.model_copy(
        update={"proposal": first.proposal.model_copy(update={"version": 2})}
    )
    _save(repository, snapshot, second)

    with real_db_session() as conn:
        rows = conn.execute(
            """
            SELECT payload_json FROM weekly_planning_input_snapshots
            WHERE organization_id = ? AND snapshot_id = ?
            """,
            (snapshot.organization_id, snapshot.snapshot_id),
        ).fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0]["payload_json"]) == snapshot.model_dump(mode="json")
    assert rows[0]["payload_json"] == json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_existing_snapshot_mismatch_is_rejected_without_overwrite() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    first_snapshot, first = _build_revision(
        snapshot_id="shared-snapshot",
        fingerprint="fingerprint-one",
    )
    _save(repository, first_snapshot, first)
    second_snapshot, second = _build_revision(
        version=2,
        snapshot_id="shared-snapshot",
        fingerprint="fingerprint-two",
    )

    with pytest.raises(WeeklyWorkforceProposalSnapshotMismatchError):
        _save(repository, second_snapshot, second)

    assert _table_count("weekly_planning_input_snapshots") == 1
    assert _table_count("weekly_workforce_proposals") == 1


def test_save_contract_organization_mismatch_is_preserved() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()
    with pytest.raises(WeeklyWorkforceProposalOrganizationMismatchError):
        repository.save_revision(
            organization_id="organization-two",
            snapshot=snapshot,
            aggregate=aggregate,
        )


def test_duplicate_revision_is_rejected_without_upsert() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()
    _save(repository, snapshot, aggregate)

    with pytest.raises(WeeklyWorkforceProposalRevisionAlreadyExistsError):
        _save(repository, snapshot, aggregate)

    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) == aggregate


def test_strict_organization_isolation_allows_same_logical_revision() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    first_snapshot, first = _build_revision(organization_id="organization-one")
    second_snapshot, second = _build_revision(organization_id="organization-two")
    _save(repository, first_snapshot, first)
    _save(repository, second_snapshot, second)

    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) == first
    assert repository.get_revision(
        organization_id="organization-two",
        proposal_id="proposal-one",
        version=1,
    ) == second
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.get_revision(
            organization_id="organization-three",
            proposal_id="proposal-one",
            version=1,
        )


def test_list_is_ascending_and_latest_is_max_without_status_semantics() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    statuses = {
        1: WeeklyWorkforceProposalStatus.APPROVED,
        2: WeeklyWorkforceProposalStatus.SUPERSEDED,
        3: WeeklyWorkforceProposalStatus.DRAFT,
    }
    for version in (3, 1, 2):
        snapshot, aggregate = _build_revision(
            version=version,
            status=statuses[version],
        )
        _save(repository, snapshot, aggregate)

    revisions = repository.list_revisions(
        organization_id="organization-one",
        proposal_id="proposal-one",
    )
    latest = repository.latest_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
    )

    assert tuple(item.proposal.version for item in revisions) == (1, 2, 3)
    assert latest.proposal.version == 3
    assert latest.proposal.status is WeeklyWorkforceProposalStatus.DRAFT


def test_missing_list_and_latest_follow_c3c_not_found_semantics() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.list_revisions(
            organization_id="organization-one",
            proposal_id="missing",
        )
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        repository.latest_revision(
            organization_id="organization-one",
            proposal_id="missing",
        )


def test_assignment_gap_and_explainability_round_trip_preserve_nested_data() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()
    _save(repository, snapshot, aggregate)
    loaded = repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assignment = loaded.assignments[0]
    gap = loaded.coverage_gaps[0]
    assert assignment == aggregate.assignments[0]
    assert assignment.demand_trace_id == aggregate.assignments[0].demand_trace_id
    assert assignment.shift_identifier is None
    assert assignment.reasons == aggregate.assignments[0].reasons
    assert gap == aggregate.coverage_gaps[0]
    assert gap.demand_trace_id == aggregate.coverage_gaps[0].demand_trace_id
    assert gap.time_window == aggregate.coverage_gaps[0].time_window
    assert loaded.eligibility_decisions == aggregate.eligibility_decisions
    assert loaded.preference_sets == aggregate.preference_sets
    assert loaded.ranked_candidates == aggregate.ranked_candidates
    assert loaded.eligibility_decisions[0].evaluations[0].evidence
    assert (
        loaded.ranked_candidates[0].eligibility_decision
        == aggregate.ranked_candidates[0].eligibility_decision
    )


@pytest.mark.parametrize(
    "failure_stage",
    ("_insert_assignments", "_insert_gaps", "_insert_explainability"),
)
def test_new_snapshot_and_revision_are_rolled_back_at_every_child_stage(
    monkeypatch,
    failure_stage: str,
) -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()

    def fail(*args, **kwargs):
        raise RuntimeError(f"forced {failure_stage} failure")

    monkeypatch.setattr(repository, failure_stage, fail)
    with pytest.raises(RuntimeError, match="forced"):
        _save(repository, snapshot, aggregate)

    assert _table_count("weekly_planning_input_snapshots") == 0
    assert _table_count("weekly_workforce_proposals") == 0
    assert _table_count("weekly_workforce_proposal_assignments") == 0
    assert _table_count("weekly_workforce_proposal_gaps") == 0
    assert _table_count("weekly_workforce_proposal_explainability") == 0


def test_preexisting_snapshot_survives_failed_revision_transaction(monkeypatch) -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, first = _build_revision(
        snapshot_id="shared-snapshot",
        fingerprint="shared-fingerprint",
    )
    _save(repository, snapshot, first)
    second = first.model_copy(
        update={"proposal": first.proposal.model_copy(update={"version": 2})}
    )

    def fail(*args, **kwargs):
        raise RuntimeError("forced gap failure")

    monkeypatch.setattr(repository, "_insert_gaps", fail)
    with pytest.raises(RuntimeError, match="forced gap"):
        _save(repository, snapshot, second)

    assert _table_count("weekly_planning_input_snapshots") == 1
    assert _table_count("weekly_workforce_proposals") == 1
    assert repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    ) == first


class _CountingConnection:
    def __init__(self, connection, calls: list[str]) -> None:
        self._connection = connection
        self._calls = calls

    def execute(self, statement, parameters=()):
        self._calls.append(statement)
        return self._connection.execute(statement, parameters)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def test_get_revision_uses_five_fixed_queries_without_n_plus_one(
    monkeypatch,
) -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()
    _save(repository, snapshot, aggregate)
    calls: list[str] = []

    @contextmanager
    def counting_session():
        with real_db_session() as conn:
            yield _CountingConnection(conn, calls)

    monkeypatch.setattr(repo_module, "db_session", counting_session)
    loaded = repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assert loaded == aggregate
    assert len(calls) == 5
    assert sum("weekly_workforce_proposal_assignments" in call for call in calls) == 1
    assert sum("weekly_workforce_proposal_explainability" in call for call in calls) == 1


def test_save_and_load_do_not_use_events_or_published_rows() -> None:
    repository = SqlWeeklyWorkforceProposalRepository()
    snapshot, aggregate = _build_revision()
    source = getsource(repo_module).casefold()

    _save(repository, snapshot, aggregate)
    repository.get_revision(
        organization_id="organization-one",
        proposal_id="proposal-one",
        version=1,
    )

    assert "weekly_workforce_proposal_events" not in source
    assert "driver_shift_planning_published_rows" not in source
    assert _table_count("weekly_workforce_proposal_events") == 0


def test_repository_has_no_current_lifecycle_or_runtime_tenant_semantics() -> None:
    source = getsource(repo_module).casefold()
    assert "current_organization_id" not in source
    assert "is_current" not in source
    assert "approve" not in source
    assert "publish" not in source
    assert "regenerate" not in source

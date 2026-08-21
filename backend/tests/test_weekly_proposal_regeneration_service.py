from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource

import pytest

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
    WeeklyProposalGenerationResult,
    WeeklyProposalRevisionCompositionError,
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
from app.services import weekly_proposal_regeneration_service as service_module
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
    regenerate_weekly_workforce_proposal,
)


ORGANIZATION_ID = "organization-one"
PROPOSAL_ID = "proposal-one"
OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY = "opaque-capability"
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)
CREATED_AT = datetime(2026, 8, 22, 9, tzinfo=timezone.utc)


def _candidate(identifier: str) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=identifier,
            capabilities=(CAPABILITY,),
        ),
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=OPERATION_DATE,
                availability=ResourceAvailability(
                    resource_identifier=identifier,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="available",
                ),
            ),
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


def _snapshot(
    *,
    snapshot_id: str,
    fingerprint: str,
    policy_identifier: str,
    policy_version: str,
    member_id: str,
) -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id=snapshot_id,
        organization_id=ORGANIZATION_ID,
        period_start=OPERATION_DATE,
        period_end=OPERATION_DATE,
        operational_unit=UNIT,
        demands=(
            OperationalDemand(
                organization_id=ORGANIZATION_ID,
                operational_unit=UNIT,
                date=OPERATION_DATE,
                time_window=WINDOW,
                capability_or_workload=CAPABILITY,
                base_quantity=1,
                target_quantity=1,
                source="normalized-source",
                applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
            ),
        ),
        workforce_candidates=(_candidate(member_id),),
        policy_set_identifier=policy_identifier,
        policy_set_version=policy_version,
        created_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        fingerprint=fingerprint,
    )


def _assignment_id_factory(**values: object) -> str:
    return (
        f"assignment:{values['operational_date'].isoformat()}:"
        f"{values['workforce_member_id']}"
    )


def _generation(snapshot: WeeklyPlanningInputSnapshot):
    return generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=_assignment_id_factory,
    )


def _aggregate(*, version: int, status=WeeklyWorkforceProposalStatus.GENERATED):
    snapshot = _snapshot(
        snapshot_id=f"snapshot-old-{version}",
        fingerprint=f"fingerprint-old-{version}",
        policy_identifier="policy-old",
        policy_version="1",
        member_id="member-old",
    )
    aggregate = compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=_generation(snapshot),
        proposal_id=PROPOSAL_ID,
        version=version,
        created_at=datetime(2026, 8, 21, 8, tzinfo=timezone.utc),
    )
    if status is not WeeklyWorkforceProposalStatus.GENERATED:
        aggregate = aggregate.model_copy(
            update={
                "proposal": aggregate.proposal.model_copy(
                    update={"status": status}
                )
            }
        )
    return aggregate


def _new_snapshot() -> WeeklyPlanningInputSnapshot:
    return _snapshot(
        snapshot_id="snapshot-new",
        fingerprint="fingerprint-new",
        policy_identifier="policy-new",
        policy_version="2",
        member_id="member-new",
    )


class InMemoryRepository:
    def __init__(self, revisions=()) -> None:
        self.revisions = {
            (
                item.proposal.organization_id,
                item.proposal.proposal_id,
                item.proposal.version,
            ): item
            for item in revisions
        }
        self.save_calls: list[tuple[str, object, object]] = []
        self.save_error: Exception | None = None

    def get_revision(self, *, organization_id, proposal_id, version):
        try:
            return self.revisions[(organization_id, proposal_id, version)]
        except KeyError as exc:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revision not found"
            ) from exc

    def list_revisions(self, *, organization_id, proposal_id):
        revisions = tuple(
            value
            for key, value in sorted(
                self.revisions.items(), key=lambda item: item[0][2]
            )
            if key[0] == organization_id and key[1] == proposal_id
        )
        if not revisions:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revisions not found"
            )
        return revisions

    def latest_revision(self, *, organization_id, proposal_id):
        return self.list_revisions(
            organization_id=organization_id,
            proposal_id=proposal_id,
        )[-1]

    def save_revision(self, *, organization_id, snapshot, aggregate):
        self.save_calls.append((organization_id, snapshot, aggregate))
        if self.save_error is not None:
            raise self.save_error
        key = (organization_id, aggregate.proposal.proposal_id, aggregate.proposal.version)
        if key in self.revisions:
            raise WeeklyWorkforceProposalRevisionAlreadyExistsError(
                "proposal revision already exists"
            )
        self.revisions[key] = aggregate
        return aggregate


def _regenerate(repository, *, previous_version=1, snapshot=None):
    return regenerate_weekly_workforce_proposal(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        previous_version=previous_version,
        snapshot=snapshot or _new_snapshot(),
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=_assignment_id_factory,
        created_at=CREATED_AT,
        repository=repository,
    )


def test_repository_fake_structurally_implements_port() -> None:
    assert isinstance(InMemoryRepository(), WeeklyWorkforceProposalRepository)


@pytest.mark.parametrize(("previous_version", "new_version"), ((1, 2), (2, 3)))
def test_regenerate_persists_next_generated_revision(
    previous_version: int,
    new_version: int,
) -> None:
    previous = _aggregate(version=previous_version)
    repository = InMemoryRepository((previous,))
    snapshot = _new_snapshot()

    result = _regenerate(
        repository,
        previous_version=previous_version,
        snapshot=snapshot,
    )

    assert result.proposal.proposal_id == previous.proposal.proposal_id
    assert result.proposal.version == new_version
    assert result.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert result.proposal.input_snapshot_id == snapshot.snapshot_id
    assert result.proposal.input_fingerprint == snapshot.fingerprint
    assert result.proposal.policy_set_identifier == snapshot.policy_set_identifier
    assert result.proposal.policy_set_version == snapshot.policy_set_version
    assert result is repository.get_revision(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        version=new_version,
    )


def test_generator_c1_composer_c4a_and_save_receive_authoritative_inputs(
    monkeypatch,
) -> None:
    previous = _aggregate(version=1)
    repository = InMemoryRepository((previous,))
    snapshot = _new_snapshot()
    generated = _generation(snapshot)
    calls: list[str] = []

    def generator_spy(**kwargs):
        calls.append("generator")
        assert kwargs["snapshot"] is snapshot
        assert kwargs["capability_mappings"] is MAPPINGS
        assert kwargs["assignment_id_factory"] is _assignment_id_factory
        return generated

    original_composer = service_module.compose_next_weekly_proposal_revision

    def composer_spy(**kwargs):
        calls.append("composer")
        assert kwargs["previous"] is previous
        assert kwargs["snapshot"] is snapshot
        assert kwargs["generation_result"] is generated
        return original_composer(**kwargs)

    monkeypatch.setattr(service_module, "generate_weekly_proposal_baseline", generator_spy)
    monkeypatch.setattr(
        service_module,
        "compose_next_weekly_proposal_revision",
        composer_spy,
    )

    result = _regenerate(repository, snapshot=snapshot)

    assert calls == ["generator", "composer"]
    assert repository.save_calls == [(ORGANIZATION_ID, snapshot, result)]


def test_previous_remains_unchanged_and_is_not_superseded() -> None:
    previous = _aggregate(
        version=1,
        status=WeeklyWorkforceProposalStatus.APPROVED,
    )
    before = previous.model_dump(mode="json")
    repository = InMemoryRepository((previous,))

    result = _regenerate(repository)

    assert previous.model_dump(mode="json") == before
    assert previous.proposal.status is WeeklyWorkforceProposalStatus.APPROVED
    assert result.proposal.status is WeeklyWorkforceProposalStatus.GENERATED


def test_stale_previous_version_is_rejected_without_save() -> None:
    first = _aggregate(version=1)
    second = _aggregate(version=2)
    repository = InMemoryRepository((first, second))

    with pytest.raises(WeeklyProposalRegenerationStaleRevisionError):
        _regenerate(repository, previous_version=1)

    assert repository.save_calls == []


def test_latest_equal_previous_version_allows_regenerate() -> None:
    repository = InMemoryRepository((_aggregate(version=2),))
    result = _regenerate(repository, previous_version=2)
    assert result.proposal.version == 3
    assert len(repository.save_calls) == 1


def test_missing_previous_not_found_is_propagated() -> None:
    repository = InMemoryRepository()
    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        _regenerate(repository)
    assert repository.save_calls == []


@pytest.mark.parametrize(
    "error",
    (
        WeeklyWorkforceProposalRevisionAlreadyExistsError("duplicate"),
        WeeklyWorkforceProposalOrganizationMismatchError("organization"),
        WeeklyWorkforceProposalSnapshotMismatchError("snapshot"),
    ),
)
def test_repository_save_errors_propagate_without_mutating_previous(error) -> None:
    previous = _aggregate(version=1)
    before = previous.model_dump(mode="json")
    repository = InMemoryRepository((previous,))
    repository.save_error = error

    with pytest.raises(type(error), match=str(error)):
        _regenerate(repository)

    assert previous.model_dump(mode="json") == before
    assert len(repository.save_calls) == 1


def test_generator_failure_is_propagated_without_save(monkeypatch) -> None:
    repository = InMemoryRepository((_aggregate(version=1),))

    def fail_generator(**kwargs):
        raise RuntimeError("generator failed")

    monkeypatch.setattr(
        service_module,
        "generate_weekly_proposal_baseline",
        fail_generator,
    )
    with pytest.raises(RuntimeError, match="generator failed"):
        _regenerate(repository)
    assert repository.save_calls == []


def test_composition_failure_is_propagated_without_save() -> None:
    repository = InMemoryRepository((_aggregate(version=1),))
    invalid_snapshot = _new_snapshot().model_copy(
        update={"organization_id": "organization-two"}
    )

    with pytest.raises(WeeklyProposalRevisionCompositionError):
        _regenerate(repository, snapshot=invalid_snapshot)

    assert repository.save_calls == []


def test_service_has_no_runtime_wiring_currentness_or_extra_side_effects() -> None:
    source = getsource(service_module).casefold()
    forbidden = (
        "sqlweeklyworkforceproposalrepository",
        "db_session",
        "current_organization_id",
        "operationaldemandprovider",
        "workforcecandidatesnapshotprovider",
        "uuid",
        "random",
        "is_current",
        "current_flag",
        "supersede",
        "approve",
        "publish",
        "fastapi",
    )
    assert all(term not in source for term in forbidden)

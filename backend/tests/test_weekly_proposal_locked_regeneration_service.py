from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource
from unittest.mock import Mock

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
    ComposedWeeklyWorkforceProposal,
    CurrentMemberContractStateSnapshot,
    LockedAssignmentUnknownDemandTraceError,
    OperationalDemand,
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyProposalRevisionCompositionError,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalRepository,
    WeeklyWorkforceProposalRepositoryError,
    WeeklyWorkforceProposalRevisionAlreadyExistsError,
    WeeklyWorkforceProposalRevisionNotFoundError,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.weekly_proposal_repository import (
    validate_weekly_workforce_proposal_save_contract,
)
from app.services import weekly_proposal_locked_regeneration_service as service_module
from app.services.weekly_proposal_locked_regeneration_service import (
    regenerate_weekly_workforce_proposal_preserving_locks,
)
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)


ORGANIZATION_ID = "organization-one"
PROPOSAL_ID = "proposal-one"
UNIT = OperationalUnit(external_identifier="unit-one")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY = "opaque-capability"
CREATED_AT = datetime(2026, 8, 24, 7, tzinfo=timezone.utc)
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)


def _demand(
    *,
    target_quantity: int = 2,
    source: str = "normalized-source",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=DAY_ONE,
        time_window=WINDOW,
        capability_or_workload=CAPABILITY,
        base_quantity=target_quantity,
        target_quantity=target_quantity,
        source=source,
        applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
    )


def _candidate(identifier: str) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=identifier,
            capabilities=(CAPABILITY,),
        ),
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=DAY_ONE,
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
    demand: OperationalDemand | None = None,
    period_end: date = DAY_TWO,
    candidates: tuple[WorkforceCandidateSnapshot, ...] | None = None,
) -> WeeklyPlanningInputSnapshot:
    selected_demand = demand if demand is not None else _demand()
    return WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-new",
        organization_id=ORGANIZATION_ID,
        period_start=DAY_ONE,
        period_end=period_end,
        operational_unit=UNIT,
        demands=(selected_demand,),
        workforce_candidates=(
            candidates
            if candidates is not None
            else (_candidate("member-a"), _candidate("member-b"))
        ),
        policy_set_identifier="policy-new",
        policy_set_version="2",
        created_at=datetime(2026, 8, 23, 8, tzinfo=timezone.utc),
        fingerprint="fingerprint-new",
    )


def _assignment(
    identifier: str,
    *,
    demand: OperationalDemand,
    member_id: str,
    locked: bool,
) -> ProposedShiftAssignment:
    return ProposedShiftAssignment(
        assignment_id=identifier,
        demand_trace_id=compute_operational_demand_trace_id(demand),
        organization_id=ORGANIZATION_ID,
        workforce_member_id=member_id,
        date=demand.date,
        operational_unit=UNIT,
        shift_identifier="dispatcher-shift",
        time_window=demand.time_window,
        capability_or_workload=demand.capability_or_workload,
        origin=ProposedShiftAssignmentOrigin.MANUAL,
        status=ProposedShiftAssignmentStatus.ACCEPTED,
        deterministic_priority=11,
        reasons=(
            ProposedAssignmentReason(
                code="dispatcher-decision",
                message="Existing dispatcher decision.",
            ),
        ),
        locked=locked,
    )


def _previous(
    *,
    version: int = 1,
    assignments: tuple[ProposedShiftAssignment, ...] = (),
) -> ComposedWeeklyWorkforceProposal:
    return ComposedWeeklyWorkforceProposal(
        proposal=WeeklyWorkforceProposal(
            proposal_id=PROPOSAL_ID,
            organization_id=ORGANIZATION_ID,
            period_start=DAY_ONE,
            period_end=DAY_TWO,
            operational_unit=UNIT,
            version=version,
            input_snapshot_id=f"snapshot-old-{version}",
            input_fingerprint=f"fingerprint-old-{version}",
            policy_set_identifier="policy-old",
            policy_set_version="1",
            status=WeeklyWorkforceProposalStatus.GENERATED,
            created_at=datetime(2026, 8, 22, 8, tzinfo=timezone.utc),
        ),
        assignments=assignments,
        coverage_gaps=(),
        eligibility_decisions=(),
        preference_sets=(),
        ranked_candidates=(),
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
        self.calls: list[str] = []
        self.save_calls: list[tuple[str, object, object]] = []
        self.save_error: Exception | None = None

    def get_revision(self, *, organization_id, proposal_id, version):
        self.calls.append("get_revision")
        try:
            return self.revisions[(organization_id, proposal_id, version)]
        except KeyError as exc:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revision not found"
            ) from exc

    def list_revisions(self, *, organization_id, proposal_id):
        values = tuple(
            value
            for key, value in sorted(
                self.revisions.items(), key=lambda item: item[0][2]
            )
            if key[0] == organization_id and key[1] == proposal_id
        )
        if not values:
            raise WeeklyWorkforceProposalRevisionNotFoundError(
                "proposal revisions not found"
            )
        return values

    def latest_revision(self, *, organization_id, proposal_id):
        self.calls.append("latest_revision")
        return self.list_revisions(
            organization_id=organization_id,
            proposal_id=proposal_id,
        )[-1]

    def save_revision(self, *, organization_id, snapshot, aggregate):
        self.calls.append("save_revision")
        self.save_calls.append((organization_id, snapshot, aggregate))
        if self.save_error is not None:
            raise self.save_error
        validate_weekly_workforce_proposal_save_contract(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=aggregate,
        )
        key = (organization_id, aggregate.proposal.proposal_id, aggregate.proposal.version)
        if key in self.revisions:
            raise WeeklyWorkforceProposalRevisionAlreadyExistsError(
                "proposal revision already exists"
            )
        self.revisions[key] = aggregate
        return aggregate


def _factory(**values: object) -> str:
    return (
        f"new:{values['operational_date'].isoformat()}:"
        f"{values['workforce_member_id']}"
    )


def _regenerate(
    repository,
    *,
    previous_version: int = 1,
    snapshot: WeeklyPlanningInputSnapshot | None = None,
    factory=_factory,
):
    return regenerate_weekly_workforce_proposal_preserving_locks(
        organization_id=ORGANIZATION_ID,
        proposal_id=PROPOSAL_ID,
        previous_version=previous_version,
        snapshot=snapshot if snapshot is not None else _snapshot(),
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=factory,
        created_at=CREATED_AT,
        repository=repository,
    )


def test_repository_fake_implements_port() -> None:
    assert isinstance(InMemoryRepository(), WeeklyWorkforceProposalRepository)


def test_previous_v1_regenerates_and_persists_v2() -> None:
    previous = _previous()
    repository = InMemoryRepository((previous,))

    result = _regenerate(repository)

    assert result.proposal.version == 2
    assert result.proposal.proposal_id == previous.proposal.proposal_id
    assert result.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert repository.calls == ["get_revision", "latest_revision", "save_revision"]


def test_previous_is_unchanged_and_not_superseded() -> None:
    previous = _previous()
    before = previous.model_dump(mode="json")
    repository = InMemoryRepository((previous,))

    _regenerate(repository)

    assert previous.model_dump(mode="json") == before
    assert previous.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert len(repository.revisions) == 2


def test_locked_preserved_unlocked_replaced_and_residual_generated_end_to_end() -> None:
    demand = _demand(target_quantity=2)
    locked = _assignment(
        "locked-one",
        demand=demand,
        member_id="locked-member",
        locked=True,
    )
    unlocked = _assignment(
        "unlocked-old",
        demand=demand,
        member_id="member-a",
        locked=False,
    )
    previous = _previous(assignments=(unlocked, locked))
    repository = InMemoryRepository((previous,))

    result = _regenerate(
        repository,
        snapshot=_snapshot(
            demand=demand,
            candidates=(
                _candidate("locked-member"),
                _candidate("member-a"),
                _candidate("member-b"),
            ),
        ),
    )

    assert locked in result.assignments
    assert all(item.assignment_id != "unlocked-old" for item in result.assignments)
    generated = next(item for item in result.assignments if not item.locked)
    assert generated.assignment_id.startswith("new:")
    assert result.coverage_gaps[0].proposed_quantity == 2
    assert result.coverage_gaps[0].gap_quantity == 0


def test_locked_overcoverage_is_preserved_end_to_end() -> None:
    demand = _demand(target_quantity=1)
    locked = tuple(
        _assignment(
            f"locked-{index}",
            demand=demand,
            member_id=f"locked-member-{index}",
            locked=True,
        )
        for index in range(2)
    )
    repository = InMemoryRepository((_previous(assignments=locked),))

    result = _regenerate(
        repository,
        snapshot=_snapshot(
            demand=demand,
            candidates=(
                _candidate("locked-member-0"),
                _candidate("locked-member-1"),
            ),
        ),
    )

    assert result.assignments == locked
    assert result.coverage_gaps[0].proposed_quantity == 2
    assert result.coverage_gaps[0].gap_quantity == -1


def test_new_snapshot_identity_fingerprint_and_policy_are_used() -> None:
    previous = _previous()
    snapshot = _snapshot()
    repository = InMemoryRepository((previous,))

    result = _regenerate(repository, snapshot=snapshot)

    assert result.proposal.input_snapshot_id == snapshot.snapshot_id
    assert result.proposal.input_fingerprint == snapshot.fingerprint
    assert result.proposal.policy_set_identifier == snapshot.policy_set_identifier
    assert result.proposal.policy_set_version == snapshot.policy_set_version
    assert repository.save_calls == [(ORGANIZATION_ID, snapshot, result)]


def test_stale_revision_fails_before_generation_or_save(monkeypatch) -> None:
    first = _previous(version=1)
    second = _previous(version=2)
    repository = InMemoryRepository((first, second))
    generator = Mock(side_effect=AssertionError("generator must not run"))
    monkeypatch.setattr(
        service_module,
        "generate_weekly_proposal_preserving_locked",
        generator,
    )

    with pytest.raises(WeeklyProposalRegenerationStaleRevisionError):
        _regenerate(repository, previous_version=1)

    generator.assert_not_called()
    assert repository.calls == ["get_revision", "latest_revision"]
    assert repository.save_calls == []


def test_latest_equal_previous_version_allows_regeneration() -> None:
    previous = _previous(version=2)
    repository = InMemoryRepository((previous,))

    result = _regenerate(repository, previous_version=2)

    assert result.proposal.version == 3
    assert len(repository.save_calls) == 1


def test_missing_previous_error_propagates() -> None:
    repository = InMemoryRepository()

    with pytest.raises(WeeklyWorkforceProposalRevisionNotFoundError):
        _regenerate(repository)

    assert repository.calls == ["get_revision"]


def test_c6b_structural_error_propagates_without_save() -> None:
    previous_demand = _demand(source="legacy-source")
    locked = _assignment(
        "locked-one",
        demand=previous_demand,
        member_id="member-a",
        locked=True,
    )
    repository = InMemoryRepository((_previous(assignments=(locked,)),))

    with pytest.raises(LockedAssignmentUnknownDemandTraceError):
        _regenerate(repository, snapshot=_snapshot(demand=_demand()))

    assert repository.save_calls == []


def test_composition_error_does_not_save() -> None:
    previous = _previous()
    repository = InMemoryRepository((previous,))
    mismatched_period = _snapshot(period_end=DAY_ONE)

    with pytest.raises(WeeklyProposalRevisionCompositionError):
        _regenerate(repository, snapshot=mismatched_period)

    assert repository.save_calls == []


def test_save_error_propagates_without_modifying_previous() -> None:
    previous = _previous()
    before = previous.model_dump(mode="json")
    repository = InMemoryRepository((previous,))
    repository.save_error = WeeklyWorkforceProposalRepositoryError("save failed")

    with pytest.raises(WeeklyWorkforceProposalRepositoryError, match="save failed"):
        _regenerate(repository)

    assert previous.model_dump(mode="json") == before
    assert len(repository.revisions) == 1


def test_factory_is_not_called_for_fully_covered_locked_demand() -> None:
    demand = _demand(target_quantity=1)
    locked = _assignment(
        "locked-one",
        demand=demand,
        member_id="member-a",
        locked=True,
    )
    repository = InMemoryRepository((_previous(assignments=(locked,)),))
    factory = Mock(side_effect=AssertionError("factory must not handle locked"))

    result = _regenerate(
        repository,
        snapshot=_snapshot(demand=demand),
        factory=factory,
    )

    assert result.assignments == (locked,)
    factory.assert_not_called()


def test_service_delegates_c6b_then_c4a_then_repository(monkeypatch) -> None:
    previous = _previous()
    snapshot = _snapshot()
    repository = InMemoryRepository((previous,))
    calls: list[str] = []
    actual_generator = service_module.generate_weekly_proposal_preserving_locked
    actual_composer = service_module.compose_next_weekly_proposal_revision

    def generator_spy(**values):
        calls.append("c6b")
        assert values["snapshot"] is snapshot
        assert values["previous"] is previous
        return actual_generator(**values)

    def composer_spy(**values):
        calls.append("c4a")
        assert values["snapshot"] is snapshot
        assert values["previous"] is previous
        return actual_composer(**values)

    monkeypatch.setattr(
        service_module,
        "generate_weekly_proposal_preserving_locked",
        generator_spy,
    )
    monkeypatch.setattr(
        service_module,
        "compose_next_weekly_proposal_revision",
        composer_spy,
    )

    _regenerate(repository, snapshot=snapshot)

    assert calls == ["c6b", "c4a"]
    assert repository.calls == ["get_revision", "latest_revision", "save_revision"]


def test_service_has_no_supersede_provider_query_uuid_api_or_sql_dependency() -> None:
    source = getsource(service_module)

    assert "supersede" not in source.casefold()
    assert "current_organization_id" not in source
    assert "provider" not in source.casefold()
    assert "uuid" not in source.casefold()
    assert "sqlalchemy" not in source.casefold()
    assert "fastapi" not in source.casefold()

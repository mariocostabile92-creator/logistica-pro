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
    WeeklyProposalRevisionCompositionError,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compose_next_weekly_proposal_revision,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning import weekly_proposal_revision


ORGANIZATION_ID = "organization-one"
PERIOD_START = date(2026, 8, 24)
PERIOD_END = date(2026, 8, 30)
OPERATION_DATE = PERIOD_START
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY = "opaque-capability"
INITIAL_CREATED_AT = datetime(2026, 8, 21, 8, tzinfo=timezone.utc)
NEXT_CREATED_AT = datetime(2026, 8, 22, 9, tzinfo=timezone.utc)


def _candidate(member_id: str) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=member_id,
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
    demand = OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=WINDOW,
        capability_or_workload=CAPABILITY,
        base_quantity=1,
        target_quantity=1,
        source="normalized-source",
        applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
    )
    return WeeklyPlanningInputSnapshot(
        snapshot_id=snapshot_id,
        organization_id=ORGANIZATION_ID,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        operational_unit=UNIT,
        demands=(demand,),
        workforce_candidates=(_candidate(member_id),),
        policy_set_identifier=policy_identifier,
        policy_set_version=policy_version,
        created_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        fingerprint=fingerprint,
    )


def _generation(snapshot: WeeklyPlanningInputSnapshot):
    def assignment_id_factory(**values: object) -> str:
        return (
            f"assignment:{snapshot.snapshot_id}:"
            f"{values['workforce_member_id']}"
        )

    return generate_weekly_proposal_baseline(
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


def _previous(*, version: int = 1, status=WeeklyWorkforceProposalStatus.GENERATED):
    snapshot = _snapshot(
        snapshot_id="snapshot-old",
        fingerprint="fingerprint-old",
        policy_identifier="policy-old",
        policy_version="1",
        member_id="member-old",
    )
    aggregate = compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=_generation(snapshot),
        proposal_id="proposal-stable",
        version=version,
        created_at=INITIAL_CREATED_AT,
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


def _next_inputs():
    snapshot = _snapshot(
        snapshot_id="snapshot-new",
        fingerprint="fingerprint-new",
        policy_identifier="policy-new",
        policy_version="2",
        member_id="member-new",
    )
    return snapshot, _generation(snapshot)


def _compose(previous=None):
    actual_previous = previous or _previous()
    snapshot, generation = _next_inputs()
    revision = compose_next_weekly_proposal_revision(
        previous=actual_previous,
        snapshot=snapshot,
        generation_result=generation,
        created_at=NEXT_CREATED_AT,
    )
    return revision, snapshot, generation


def test_next_revision_preserves_identity_scope_and_uses_new_inputs() -> None:
    previous = _previous()
    revision, snapshot, _ = _compose(previous)
    proposal = revision.proposal

    assert proposal.proposal_id == previous.proposal.proposal_id
    assert proposal.version == 2
    assert proposal.organization_id == previous.proposal.organization_id
    assert proposal.period_start == previous.proposal.period_start
    assert proposal.period_end == previous.proposal.period_end
    assert proposal.operational_unit == previous.proposal.operational_unit
    assert proposal.input_snapshot_id == snapshot.snapshot_id
    assert proposal.input_fingerprint == snapshot.fingerprint
    assert proposal.policy_set_identifier == snapshot.policy_set_identifier
    assert proposal.policy_set_version == snapshot.policy_set_version
    assert proposal.created_at == NEXT_CREATED_AT
    assert proposal.status is WeeklyWorkforceProposalStatus.GENERATED


@pytest.mark.parametrize(("previous_version", "expected"), ((1, 2), (2, 3)))
def test_version_is_exactly_previous_plus_one(
    previous_version: int,
    expected: int,
) -> None:
    revision, _, _ = _compose(_previous(version=previous_version))
    assert revision.proposal.version == expected


@pytest.mark.parametrize(
    "previous_status",
    (
        WeeklyWorkforceProposalStatus.APPROVED,
        WeeklyWorkforceProposalStatus.SUPERSEDED,
    ),
)
def test_previous_lifecycle_status_does_not_change_generated_revision_status(
    previous_status: WeeklyWorkforceProposalStatus,
) -> None:
    previous = _previous(status=previous_status)
    previous_before = previous.model_dump(mode="json")

    revision, _, _ = _compose(previous)

    assert revision.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert previous.proposal.status is previous_status
    assert previous.model_dump(mode="json") == previous_before


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("organization_id", "organization-two", "organization"),
        ("period_start", date(2026, 8, 23), "period_start"),
        ("period_end", date(2026, 8, 31), "period_end"),
        (
            "operational_unit",
            OperationalUnit(external_identifier="unit-two"),
            "operational unit",
        ),
    ),
)
def test_snapshot_scope_mismatch_is_rejected_deterministically(
    field: str,
    value: object,
    message: str,
) -> None:
    previous = _previous()
    snapshot, generation = _next_inputs()
    invalid_snapshot = snapshot.model_copy(update={field: value})

    with pytest.raises(WeeklyProposalRevisionCompositionError, match=message):
        compose_next_weekly_proposal_revision(
            previous=previous,
            snapshot=invalid_snapshot,
            generation_result=generation,
            created_at=NEXT_CREATED_AT,
        )


def test_new_artifacts_come_only_from_new_generation_result() -> None:
    previous = _previous()
    revision, _, generation = _compose(previous)

    assert revision.assignments == generation.assignments
    assert revision.coverage_gaps == generation.coverage_gaps
    assert revision.eligibility_decisions == generation.eligibility_decisions
    assert revision.preference_sets == generation.preference_sets
    assert revision.ranked_candidates == generation.ranked_candidates
    assert revision.assignments != previous.assignments
    assert revision.assignments[0].workforce_member_id == "member-new"


def test_all_inputs_remain_immutable_and_unchanged() -> None:
    previous = _previous()
    snapshot, generation = _next_inputs()
    previous_before = previous.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")
    generation_before = generation.model_dump(mode="json")

    compose_next_weekly_proposal_revision(
        previous=previous,
        snapshot=snapshot,
        generation_result=generation,
        created_at=NEXT_CREATED_AT,
    )

    assert previous.model_dump(mode="json") == previous_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert generation.model_dump(mode="json") == generation_before


def test_revision_contract_is_pure_and_has_no_runtime_or_persistence_semantics() -> None:
    source = getsource(weekly_proposal_revision).casefold()
    forbidden = (
        "uuid",
        "random",
        "db_session",
        "repository",
        "sql",
        "current_organization_id",
        "supersede",
        "approve",
        "publish",
        "lock",
        "fastapi",
    )
    assert all(term not in source for term in forbidden)

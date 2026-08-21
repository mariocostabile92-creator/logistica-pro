from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

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
    WeeklyProposalCompositionError,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compute_operational_demand_trace_id,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
)


ORGANIZATION_ID = "organization-one"
OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
OTHER_UNIT = OperationalUnit(external_identifier="unit-two")
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)
CAPABILITY = "opaque-capability"
CREATED_AT = datetime(2026, 8, 21, 9, 30, tzinfo=timezone.utc)


def _candidate() -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier="member-one",
            capabilities=(CAPABILITY,),
        ),
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=OPERATION_DATE,
                availability=ResourceAvailability(
                    resource_identifier="member-one",
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


def _demand() -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=WINDOW,
        capability_or_workload=CAPABILITY,
        base_quantity=1,
        target_quantity=1,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="policy-one"),
    )


def _snapshot() -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-one",
        organization_id=ORGANIZATION_ID,
        period_start=OPERATION_DATE,
        period_end=OPERATION_DATE,
        operational_unit=UNIT,
        demands=(_demand(),),
        workforce_candidates=(_candidate(),),
        policy_set_identifier="policy-set-one",
        policy_set_version="version-one",
        created_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        fingerprint="authoritative-fingerprint",
    )


def _assignment_id_factory(**values: object) -> str:
    return (
        f"assignment:{values['operational_date'].isoformat()}:"
        f"{values['workforce_member_id']}"
    )


def _generation_result(snapshot: WeeklyPlanningInputSnapshot):
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
        assignment_id_factory=_assignment_id_factory,
    )


def _compose(snapshot=None, generation_result=None):
    actual_snapshot = snapshot or _snapshot()
    actual_generation_result = generation_result or _generation_result(
        actual_snapshot
    )
    return compose_weekly_workforce_proposal(
        snapshot=actual_snapshot,
        generation_result=actual_generation_result,
        proposal_id="proposal-one",
        version=3,
        created_at=CREATED_AT,
    )


def test_valid_inputs_produce_generated_proposal_with_preserved_header():
    snapshot = _snapshot()
    composed = _compose(snapshot=snapshot)
    proposal = composed.proposal

    assert proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert proposal.proposal_id == "proposal-one"
    assert proposal.version == 3
    assert proposal.created_at == CREATED_AT
    assert proposal.organization_id == snapshot.organization_id
    assert proposal.period_start == snapshot.period_start
    assert proposal.period_end == snapshot.period_end
    assert proposal.operational_unit == snapshot.operational_unit
    assert proposal.input_snapshot_id == snapshot.snapshot_id
    assert proposal.input_fingerprint == snapshot.fingerprint
    assert proposal.policy_set_identifier == snapshot.policy_set_identifier
    assert proposal.policy_set_version == snapshot.policy_set_version


def test_snapshot_reference_changes_only_with_snapshot_id():
    first_snapshot = _snapshot()
    second_snapshot = first_snapshot.model_copy(
        update={"snapshot_id": "snapshot-two"}
    )

    first = _compose(snapshot=first_snapshot).proposal
    second = _compose(snapshot=second_snapshot).proposal

    assert first.input_snapshot_id == "snapshot-one"
    assert second.input_snapshot_id == "snapshot-two"
    assert first.input_snapshot_id != second.input_snapshot_id
    assert first.input_fingerprint == second.input_fingerprint
    assert first.input_snapshot_id != first.input_fingerprint


def test_generation_content_and_order_are_preserved_without_copying_semantics():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    composed = _compose(snapshot=snapshot, generation_result=generated)

    assert composed.assignments == generated.assignments
    assert composed.coverage_gaps == generated.coverage_gaps
    assert composed.eligibility_decisions == generated.eligibility_decisions
    assert composed.preference_sets == generated.preference_sets
    assert composed.ranked_candidates == generated.ranked_candidates


def test_composer_accepts_only_canonical_snapshot_demand_traces():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    expected_trace = compute_operational_demand_trace_id(snapshot.demands[0])

    composed = _compose(snapshot=snapshot, generation_result=generated)

    collections = (
        composed.assignments,
        composed.coverage_gaps,
        composed.eligibility_decisions,
        composed.preference_sets,
        composed.ranked_candidates,
    )
    assert all(
        item.demand_trace_id == expected_trace
        for collection in collections
        for item in collection
    )


@pytest.mark.parametrize(
    ("field", "subject"),
    (
        ("assignments", "assignment demand trace"),
        ("coverage_gaps", "coverage gap demand trace"),
        ("eligibility_decisions", "eligibility decision demand trace"),
        ("preference_sets", "preference set demand trace"),
        ("ranked_candidates", "ranked candidate demand trace"),
    ),
)
def test_composer_rejects_artifact_trace_not_present_in_snapshot(
    field,
    subject,
):
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    artifact = getattr(generated, field)[0].model_copy(
        update={"demand_trace_id": "unknown-demand-trace"}
    )
    invalid_result = generated.model_copy(update={field: (artifact,)})

    with pytest.raises(WeeklyProposalCompositionError, match=subject):
        _compose(snapshot=snapshot, generation_result=invalid_result)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("organization_id", "other-organization", "assignment organization"),
        ("operational_unit", OTHER_UNIT, "assignment operational unit"),
        (
            "date",
            OPERATION_DATE + timedelta(days=1),
            "assignment date",
        ),
    ),
)
def test_assignment_scope_mismatch_is_rejected(field, value, message):
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    invalid_assignment = generated.assignments[0].model_copy(
        update={field: value}
    )
    invalid_result = generated.model_copy(
        update={"assignments": (invalid_assignment,)}
    )

    with pytest.raises(WeeklyProposalCompositionError, match=message):
        _compose(snapshot=snapshot, generation_result=invalid_result)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("organization_id", "other-organization", "coverage gap organization"),
        ("operational_unit", OTHER_UNIT, "coverage gap operational unit"),
        (
            "date",
            OPERATION_DATE + timedelta(days=1),
            "coverage gap date",
        ),
    ),
)
def test_coverage_gap_scope_mismatch_is_rejected(field, value, message):
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    invalid_gap = generated.coverage_gaps[0].model_copy(update={field: value})
    invalid_result = generated.model_copy(
        update={"coverage_gaps": (invalid_gap,)}
    )

    with pytest.raises(WeeklyProposalCompositionError, match=message):
        _compose(snapshot=snapshot, generation_result=invalid_result)


def test_eligibility_decision_organization_mismatch_is_rejected():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    invalid = generated.eligibility_decisions[0].model_copy(
        update={"organization_id": "other-organization"}
    )
    invalid_result = generated.model_copy(
        update={"eligibility_decisions": (invalid,)}
    )

    with pytest.raises(
        WeeklyProposalCompositionError,
        match="eligibility decision organization",
    ):
        _compose(snapshot=snapshot, generation_result=invalid_result)


def test_preference_set_unknown_member_is_rejected():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    invalid = generated.preference_sets[0].model_copy(
        update={"workforce_member_id": "unknown-member"}
    )
    invalid_result = generated.model_copy(
        update={"preference_sets": (invalid,)}
    )

    with pytest.raises(
        WeeklyProposalCompositionError,
        match="preference set workforce member",
    ):
        _compose(snapshot=snapshot, generation_result=invalid_result)


def test_ranked_candidate_organization_mismatch_is_rejected():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    ranked = generated.ranked_candidates[0]
    invalid_candidate = ranked.candidate.model_copy(
        update={"organization_id": "other-organization"}
    )
    invalid_ranked = ranked.model_copy(update={"candidate": invalid_candidate})
    invalid_result = generated.model_copy(
        update={"ranked_candidates": (invalid_ranked,)}
    )

    with pytest.raises(
        WeeklyProposalCompositionError,
        match="ranked candidate organization",
    ):
        _compose(snapshot=snapshot, generation_result=invalid_result)


def test_snapshot_generation_result_and_nested_content_are_not_mutated():
    snapshot = _snapshot()
    generated = _generation_result(snapshot)
    snapshot_before = snapshot.model_dump(mode="json")
    generated_before = generated.model_dump(mode="json")

    _compose(snapshot=snapshot, generation_result=generated)

    assert snapshot.model_dump(mode="json") == snapshot_before
    assert generated.model_dump(mode="json") == generated_before


def test_composed_output_and_collections_are_immutable():
    composed = _compose()

    with pytest.raises(ValidationError):
        composed.assignments = ()
    with pytest.raises(TypeError):
        composed.assignments[0] = composed.assignments[0]
    with pytest.raises(ValidationError):
        composed.proposal.status = WeeklyWorkforceProposalStatus.APPROVED


def test_composer_has_no_fingerprint_recalculation_runtime_or_persistence():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "weekly_proposal_composer.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden = (
        "compute_weekly_planning_input_fingerprint",
        "uuid",
        "random",
        "datetime.now",
        "repository",
        "sqlalchemy",
        "fastapi",
        "database",
        "persist",
    )
    assert all(item not in source for item in forbidden)

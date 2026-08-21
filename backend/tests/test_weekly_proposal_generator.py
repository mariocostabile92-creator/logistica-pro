from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

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
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkforceEligibilityDecision,
    WorkloadCapabilityMapping,
    compute_operational_demand_trace_id,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning import weekly_proposal_generator


ORGANIZATION_ID = "organization-one"
OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one")
CAPABILITY = "opaque-capability"
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)


def _window(
    identifier: str = "window-one",
    *,
    starts_at: str | None = "08:00",
    ends_at: str | None = "12:00",
) -> TimeWindow:
    return TimeWindow(
        external_identifier=identifier,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def _demand(
    *,
    target_quantity: int = 1,
    window: TimeWindow | None = None,
    source: str = "normalized-demand",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=window or _window(),
        capability_or_workload=CAPABILITY,
        base_quantity=target_quantity,
        target_quantity=target_quantity,
        source=source,
        applied_policy=AppliedPolicyMetadata(identifier="policy-one"),
    )


def _candidate(
    identifier: str,
    *,
    callable_on_date: bool = True,
    assigned_minutes: Decimal = Decimal("0"),
    recent_consecutivity: int = 0,
) -> WorkforceCandidateSnapshot:
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
                    available=callable_on_date,
                    observed_state=(
                        "available" if callable_on_date else "unavailable"
                    ),
                    reason="Authoritative daily readiness.",
                    origin="workforce",
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
        recent_consecutivity=recent_consecutivity,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=assigned_minutes,
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _snapshot(
    *,
    demands: tuple[OperationalDemand, ...],
    candidates: tuple[WorkforceCandidateSnapshot, ...],
    snapshot_id: str = "snapshot-one",
) -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id=snapshot_id,
        organization_id=ORGANIZATION_ID,
        period_start=OPERATION_DATE,
        period_end=OPERATION_DATE,
        operational_unit=UNIT,
        demands=demands,
        workforce_candidates=candidates,
        policy_set_identifier="policy-set-one",
        policy_set_version="1",
        created_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        fingerprint="stable-fingerprint",
    )


def _assignment_id_factory(**values: object) -> str:
    operational_date = values["operational_date"]
    time_window = values["time_window"]
    return (
        f"assignment:{operational_date.isoformat()}:"
        f"{time_window.external_identifier}:"
        f"{values['workforce_member_id']}:"
        f"{values['deterministic_priority']}"
    )


def _generate(
    snapshot: WeeklyPlanningInputSnapshot,
    *,
    factory=_assignment_id_factory,
):
    return generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=factory,
    )


def _three_candidates() -> tuple[WorkforceCandidateSnapshot, ...]:
    return (
        _candidate("member-a", assigned_minutes=Decimal("0")),
        _candidate("member-b", assigned_minutes=Decimal("60")),
        _candidate("member-c", assigned_minutes=Decimal("120")),
    )


def test_target_two_with_three_eligible_creates_two_assignments():
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=2),),
            candidates=_three_candidates(),
        )
    )

    assert [item.workforce_member_id for item in result.assignments] == [
        "member-a",
        "member-b",
    ]
    assert result.coverage_gaps[0].proposed_quantity == 2
    assert result.coverage_gaps[0].gap_quantity == 0


def test_target_three_with_two_eligible_creates_gap_one():
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=3),),
            candidates=_three_candidates()[:2],
        )
    )

    assert len(result.assignments) == 2
    assert result.coverage_gaps[0].required_quantity == 3
    assert result.coverage_gaps[0].proposed_quantity == 2
    assert result.coverage_gaps[0].gap_quantity == 1
    assert "eligible cohort size: 2" in result.coverage_gaps[0].reason.message


def test_zero_target_creates_no_assignment_and_does_not_call_factory():
    factory = Mock(side_effect=_assignment_id_factory)
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=0),),
            candidates=_three_candidates(),
        ),
        factory=factory,
    )

    assert result.assignments == ()
    assert result.coverage_gaps[0].gap_quantity == 0
    factory.assert_not_called()


def test_non_eligible_candidate_is_never_selected():
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=2),),
            candidates=(
                _candidate("member-a", callable_on_date=False),
                _candidate("member-b"),
            ),
        )
    )

    assert [item.workforce_member_id for item in result.assignments] == [
        "member-b"
    ]
    excluded = next(
        item
        for item in result.eligibility_decisions
        if item.workforce_member_id == "member-a"
    )
    assert excluded.eligible is False


def test_generator_uses_c1b_and_b3_once_for_each_demand():
    snapshot = _snapshot(
        demands=(_demand(target_quantity=1),),
        candidates=_three_candidates(),
    )
    original_composer = (
        weekly_proposal_generator.build_baseline_workforce_preference_sets
    )
    original_ranking = (
        weekly_proposal_generator.rank_eligible_workforce_candidates
    )
    with (
        patch.object(
            weekly_proposal_generator,
            "build_baseline_workforce_preference_sets",
            wraps=original_composer,
        ) as composer,
        patch.object(
            weekly_proposal_generator,
            "rank_eligible_workforce_candidates",
            wraps=original_ranking,
        ) as ranking,
    ):
        result = _generate(snapshot)

    assert composer.call_count == 1
    assert ranking.call_count == 1
    assert result.assignments[0].workforce_member_id == (
        result.ranked_candidates[0].workforce_member_id
    )


def test_b3_rank_selects_lower_load_before_lexical_tie_break():
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=1),),
            candidates=(
                _candidate("a-higher-load", assigned_minutes=Decimal("120")),
                _candidate("z-lower-load", assigned_minutes=Decimal("0")),
            ),
        )
    )

    assert result.ranked_candidates[0].workforce_member_id == "z-lower-load"
    assert result.assignments[0].workforce_member_id == "z-lower-load"


def test_assignment_contract_and_identity_are_populated_from_selection():
    factory = Mock(side_effect=_assignment_id_factory)
    result = _generate(
        _snapshot(
            demands=(_demand(),),
            candidates=(_candidate("member-a"),),
        ),
        factory=factory,
    )
    assignment = result.assignments[0]

    assert assignment.assignment_id.startswith("assignment:")
    assert assignment.shift_identifier is None
    assert assignment.origin is ProposedShiftAssignmentOrigin.AUTOMATIC
    assert assignment.status is ProposedShiftAssignmentStatus.PROPOSED
    assert assignment.locked is False
    assert assignment.deterministic_priority == 1
    assert [reason.code for reason in assignment.reasons[:2]] == [
        "candidate-eligible",
        "deterministic-rank",
    ]
    factory.assert_called_once()
    assert factory.call_args.kwargs["workforce_member_id"] == "member-a"
    assert factory.call_args.kwargs["deterministic_priority"] == 1


def test_all_generated_artifacts_share_their_authoritative_demand_trace():
    first = _demand(source="source-one")
    second = _demand(source="source-two")
    snapshot = _snapshot(
        demands=(first, second),
        candidates=_three_candidates()[:2],
    )

    result = _generate(snapshot)
    expected = {
        compute_operational_demand_trace_id(first),
        compute_operational_demand_trace_id(second),
    }

    assert {item.demand_trace_id for item in result.assignments} == expected
    assert {item.demand_trace_id for item in result.coverage_gaps} == expected
    assert {
        item.demand_trace_id for item in result.eligibility_decisions
    } == expected
    assert {item.demand_trace_id for item in result.preference_sets} == expected
    assert {
        item.demand_trace_id for item in result.ranked_candidates
    } == expected


def test_demand_trace_depends_on_source_but_not_quantities():
    demand = _demand(target_quantity=1, source="source-one")
    different_source = demand.model_copy(update={"source": "source-two"})
    different_quantities = demand.model_copy(
        update={"base_quantity": 7, "target_quantity": 9}
    )

    assert compute_operational_demand_trace_id(demand) != (
        compute_operational_demand_trace_id(different_source)
    )
    assert compute_operational_demand_trace_id(demand) == (
        compute_operational_demand_trace_id(different_quantities)
    )


def test_candidate_is_not_duplicated_for_the_same_demand():
    result = _generate(
        _snapshot(
            demands=(_demand(target_quantity=3),),
            candidates=(_candidate("member-a"),),
        )
    )

    assert [item.workforce_member_id for item in result.assignments] == [
        "member-a"
    ]
    assert result.coverage_gaps[0].gap_quantity == 2


def test_non_overlapping_assignments_for_same_member_are_allowed():
    morning = _demand(
        window=_window("a-morning", starts_at="08:00", ends_at="12:00")
    )
    afternoon = _demand(
        window=_window("b-afternoon", starts_at="12:00", ends_at="16:00")
    )

    result = _generate(
        _snapshot(
            demands=(afternoon, morning),
            candidates=(_candidate("member-a"),),
        )
    )

    assert len(result.assignments) == 2
    assert [item.time_window.external_identifier for item in result.assignments] == [
        "a-morning",
        "b-afternoon",
    ]


def test_overlapping_assignment_is_skipped_and_creates_gap():
    first = _demand(
        window=_window("a-first", starts_at="08:00", ends_at="12:00")
    )
    overlapping = _demand(
        window=_window("b-overlap", starts_at="10:00", ends_at="14:00")
    )

    result = _generate(
        _snapshot(
            demands=(overlapping, first),
            candidates=(_candidate("member-a"),),
        )
    )

    assert len(result.assignments) == 1
    assert result.coverage_gaps[1].gap_quantity == 1
    assert "skipped for intra-run conflict: 1" in (
        result.coverage_gaps[1].reason.message
    )
    assert "intra-run-conflict" in (
        result.coverage_gaps[1].excluded_candidate_categories
    )


def test_when_rank_one_conflicts_rank_two_is_selected():
    first = _demand(
        window=_window("a-first", starts_at="08:00", ends_at="12:00")
    )
    overlapping = _demand(
        window=_window("b-overlap", starts_at="10:00", ends_at="14:00")
    )
    result = _generate(
        _snapshot(
            demands=(first, overlapping),
            candidates=(
                _candidate("member-a", assigned_minutes=Decimal("0")),
                _candidate("member-b", assigned_minutes=Decimal("60")),
            ),
        )
    )

    assert [item.workforce_member_id for item in result.assignments] == [
        "member-a",
        "member-b",
    ]
    assert result.coverage_gaps[1].gap_quantity == 0


def test_unknown_intra_run_conflict_is_fail_closed():
    complete = _demand(
        window=_window("a-complete", starts_at="08:00", ends_at="12:00")
    )
    incomplete = _demand(
        window=_window("b-incomplete", starts_at="12:00", ends_at=None)
    )
    candidate = _candidate("member-a")

    def force_eligible(*, candidate, demand, capability_mappings):
        return WorkforceEligibilityDecision(
            demand_trace_id=(
                weekly_proposal_generator
                .compute_operational_demand_trace_id(demand)
            ),
            organization_id=demand.organization_id,
            workforce_member_id=candidate.workforce_member_id,
            operational_date=demand.date,
            operational_unit=demand.operational_unit,
            time_window=demand.time_window,
            capability_or_workload=demand.capability_or_workload,
            eligible=True,
        )

    with patch.object(
        weekly_proposal_generator,
        "evaluate_workforce_candidate_eligibility",
        side_effect=force_eligible,
    ):
        result = _generate(
            _snapshot(
                demands=(incomplete, complete),
                candidates=(candidate,),
            )
        )

    assert len(result.assignments) == 1
    assert result.coverage_gaps[1].gap_quantity == 1
    assert "intra-run-conflict" in (
        result.coverage_gaps[1].excluded_candidate_categories
    )


def test_reversed_demand_order_produces_same_output():
    first = _demand(
        window=_window("a-first", starts_at="08:00", ends_at="12:00")
    )
    second = _demand(
        window=_window("b-second", starts_at="12:00", ends_at="16:00")
    )
    candidates = _three_candidates()

    assert _generate(
        _snapshot(demands=(first, second), candidates=candidates)
    ) == _generate(
        _snapshot(demands=(second, first), candidates=candidates)
    )


def test_reversed_candidate_order_produces_same_output():
    candidates = _three_candidates()

    assert _generate(
        _snapshot(demands=(_demand(target_quantity=2),), candidates=candidates)
    ) == _generate(
        _snapshot(
            demands=(_demand(target_quantity=2),),
            candidates=tuple(reversed(candidates)),
        )
    )


def test_snapshot_and_nested_inputs_are_not_mutated():
    snapshot = _snapshot(
        demands=(_demand(target_quantity=2),),
        candidates=_three_candidates(),
    )
    before = snapshot.model_dump(mode="json")

    result = _generate(snapshot)

    assert snapshot.model_dump(mode="json") == before
    with pytest.raises(ValidationError):
        result.assignments = ()
    with pytest.raises(TypeError):
        result.assignments[0] = result.assignments[0]


def test_generator_is_pure_and_has_no_forbidden_dependencies_or_scoring():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "weekly_proposal_generator.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden = (
        "uuid4",
        "random",
        "datetime.now",
        "score",
        "weighted",
        "repository",
        "sqlalchemy",
        "fastapi",
        "database",
        "vehicle",
    )
    assert all(item not in source for item in forbidden)

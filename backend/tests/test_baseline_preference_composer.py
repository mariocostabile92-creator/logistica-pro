from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.domain.core_language import HumanResource, OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    PlanningPreferenceOutcome,
    WorkforceCandidateSnapshot,
    build_baseline_workforce_preference_sets,
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning import baseline_preference_composer


OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one")
WINDOW = TimeWindow(
    external_identifier="window-one",
    starts_at="08:00",
    ends_at="12:00",
)


def _demand() -> OperationalDemand:
    return OperationalDemand(
        organization_id="organization-one",
        operational_unit=UNIT,
        date=OPERATION_DATE,
        time_window=WINDOW,
        capability_or_workload="opaque-capability",
        base_quantity=1,
        target_quantity=1,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="policy-one"),
    )


def _candidate(
    identifier: str,
    *,
    assigned_minutes: Decimal | None = Decimal("0"),
    recent_consecutivity: int | None = 0,
) -> WorkforceCandidateSnapshot:
    assigned_time = (
        AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN)
        if assigned_minutes is None
        else AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=assigned_minutes,
            unit=AssignedTimeUnit.MINUTES,
        )
    )
    return WorkforceCandidateSnapshot(
        organization_id="organization-one",
        human_resource=HumanResource(external_identifier=identifier),
        applicable_contract_state=CurrentMemberContractStateSnapshot(),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=recent_consecutivity,
        already_assigned_minutes_or_hours=assigned_time,
    )


def _compose(
    *candidates: WorkforceCandidateSnapshot,
):
    return build_baseline_workforce_preference_sets(
        candidates=candidates,
        demand=_demand(),
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
    )


def _outcomes_by_member(result, code: str):
    return {
        item.workforce_member_id: next(
            evaluation.outcome
            for evaluation in item.evaluations
            if evaluation.code == code
        )
        for item in result
    }


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        (
            (Decimal("1"), Decimal("2"), Decimal("3")),
            (
                PlanningPreferenceOutcome.PREFERRED,
                PlanningPreferenceOutcome.DEPRIORITIZED,
                PlanningPreferenceOutcome.DEPRIORITIZED,
            ),
        ),
        (
            (Decimal("1"), Decimal("1"), Decimal("3")),
            (
                PlanningPreferenceOutcome.PREFERRED,
                PlanningPreferenceOutcome.PREFERRED,
                PlanningPreferenceOutcome.DEPRIORITIZED,
            ),
        ),
        (
            (Decimal("2"), Decimal("2"), Decimal("2")),
            (
                PlanningPreferenceOutcome.NEUTRAL,
                PlanningPreferenceOutcome.NEUTRAL,
                PlanningPreferenceOutcome.NEUTRAL,
            ),
        ),
    ),
)
def test_lower_load_cohort_aggregation(values, expected):
    candidates = tuple(
        _candidate(f"member-{index}", assigned_minutes=value)
        for index, value in enumerate(values, start=1)
    )

    outcomes = _outcomes_by_member(_compose(*candidates), "lower-weekly-load")

    assert tuple(outcomes.values()) == expected


def test_unknown_load_remains_neutral_and_is_not_zero():
    unknown = _candidate("member-a", assigned_minutes=None)
    known = _candidate("member-b", assigned_minutes=Decimal("1"))

    outcomes = _outcomes_by_member(
        _compose(unknown, known),
        "lower-weekly-load",
    )

    assert outcomes == {
        "member-a": PlanningPreferenceOutcome.NEUTRAL,
        "member-b": PlanningPreferenceOutcome.NEUTRAL,
    }


def test_continuity_uses_the_same_mandatory_aggregation():
    result = _compose(
        _candidate("member-1", recent_consecutivity=1),
        _candidate("member-2", recent_consecutivity=2),
        _candidate("member-3", recent_consecutivity=3),
    )

    assert tuple(
        _outcomes_by_member(result, "continuity").values()
    ) == (
        PlanningPreferenceOutcome.PREFERRED,
        PlanningPreferenceOutcome.DEPRIORITIZED,
        PlanningPreferenceOutcome.DEPRIORITIZED,
    )


def test_existing_assignment_stability_is_evaluated_once_per_candidate():
    candidates = (_candidate("member-a"), _candidate("member-b"))
    original = (
        baseline_preference_composer
        .evaluate_existing_assignment_stability_preference
    )
    with patch.object(
        baseline_preference_composer,
        "evaluate_existing_assignment_stability_preference",
        wraps=original,
    ) as evaluator:
        _compose(*candidates)

    assert evaluator.call_count == len(candidates)


def test_each_candidate_receives_exactly_three_ordered_unique_evaluations():
    result = _compose(_candidate("member-a"), _candidate("member-b"))

    for item in result:
        identities = tuple(
            (evaluation.priority, evaluation.code)
            for evaluation in item.evaluations
        )
        assert [evaluation.code for evaluation in item.evaluations] == [
            "existing-assignment-stability",
            "lower-weekly-load",
            "continuity",
        ]
        assert len(identities) == len(set(identities)) == 3


def test_all_preference_sets_use_the_canonical_demand_trace():
    demand = _demand()
    result = build_baseline_workforce_preference_sets(
        candidates=(_candidate("member-a"), _candidate("member-b")),
        demand=demand,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
    )

    assert {item.demand_trace_id for item in result} == {
        compute_operational_demand_trace_id(demand)
    }


def test_input_order_does_not_change_output_or_evidence():
    first = _candidate("member-a", assigned_minutes=Decimal("1"))
    second = _candidate("member-b", assigned_minutes=Decimal("2"))
    third = _candidate("member-c", assigned_minutes=Decimal("3"))

    assert _compose(first, second, third) == _compose(third, first, second)


def test_external_identifier_only_controls_deterministic_order():
    first = _candidate("z-member", assigned_minutes=Decimal("1"))
    second = _candidate("a-member", assigned_minutes=Decimal("1"))
    result = _compose(first, second)

    assert [item.workforce_member_id for item in result] == [
        "a-member",
        "z-member",
    ]
    assert set(_outcomes_by_member(result, "lower-weekly-load").values()) == {
        PlanningPreferenceOutcome.NEUTRAL
    }


def test_aggregated_evidence_contains_counts_and_pairwise_details():
    result = _compose(
        _candidate("member-a", assigned_minutes=Decimal("1")),
        _candidate("member-b", assigned_minutes=Decimal("2")),
        _candidate("member-c", assigned_minutes=Decimal("3")),
    )
    evaluation = next(
        item
        for item in result[1].evaluations
        if item.code == "lower-weekly-load"
    )
    evidence = {item.key: item.value for item in evaluation.evidence}

    assert evidence["comparison-count"] == 2
    assert evidence["preferred-count"] == 1
    assert evidence["deprioritized-count"] == 1
    assert evidence["comparison-1:workforce-member-id"] == "member-a"
    assert evidence["comparison-2:workforce-member-id"] == "member-c"


def test_duplicate_member_is_rejected_deterministically():
    member = _candidate("member-a")

    with pytest.raises(ValueError, match="duplicate workforce member"):
        _compose(member, member)


def test_output_is_immutable():
    result = _compose(_candidate("member-a"))

    with pytest.raises(ValidationError):
        result[0].workforce_member_id = "other"
    with pytest.raises(TypeError):
        result[0].evaluations[0] = result[0].evaluations[0]


def test_composer_has_no_ranking_scoring_persistence_or_external_terms():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "baseline_preference_composer.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden = (
        "candidate_ranking",
        "rank_eligible",
        "score",
        "weighted",
        "repository",
        "sqlalchemy",
        "fastapi",
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
    )
    assert all(item not in source for item in forbidden)

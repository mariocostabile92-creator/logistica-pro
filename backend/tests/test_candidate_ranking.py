from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import HumanResource, OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    CurrentMemberContractStateSnapshot,
    DeterministicCandidateRankingKey,
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
    PreferenceRankingKeyEntry,
    WorkforceCandidateRankingInput,
    WorkforceCandidateSnapshot,
    WorkforceEligibilityDecision,
    WorkforcePlanningPreferenceSet,
    rank_eligible_workforce_candidates,
)


OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-one")
WINDOW = TimeWindow(external_identifier="window-one")
DEMAND_TRACE_ID = "demand-trace-one"


def _candidate(member_id: str) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id="organization-one",
        human_resource=HumanResource(external_identifier=member_id),
        applicable_contract_state=CurrentMemberContractStateSnapshot(),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.UNKNOWN
        ),
    )


def _decision(
    member_id: str,
    *,
    eligible: bool = True,
    operational_date: date = OPERATION_DATE,
    demand_trace_id: str = DEMAND_TRACE_ID,
) -> WorkforceEligibilityDecision:
    return WorkforceEligibilityDecision(
        demand_trace_id=demand_trace_id,
        organization_id="organization-one",
        workforce_member_id=member_id,
        operational_date=operational_date,
        operational_unit=UNIT,
        time_window=WINDOW,
        capability_or_workload="opaque-capability",
        eligible=eligible,
    )


def _preference(
    code: str,
    priority: int,
    outcome: PlanningPreferenceOutcome,
) -> PlanningPreferenceEvaluation:
    return PlanningPreferenceEvaluation(
        code=code,
        outcome=outcome,
        priority=priority,
        message="Deterministic preference evaluation.",
        rule_origin="core-policy",
    )


def _input(
    member_id: str,
    *evaluations: PlanningPreferenceEvaluation,
    eligible: bool = True,
    preference_member_id: str | None = None,
    preference_date: date = OPERATION_DATE,
    decision_date: date = OPERATION_DATE,
    decision_trace_id: str = DEMAND_TRACE_ID,
    preference_trace_id: str = DEMAND_TRACE_ID,
) -> WorkforceCandidateRankingInput:
    return WorkforceCandidateRankingInput(
        candidate=_candidate(member_id),
        eligibility_decision=_decision(
            member_id,
            eligible=eligible,
            operational_date=decision_date,
            demand_trace_id=decision_trace_id,
        ),
        preference_set=WorkforcePlanningPreferenceSet(
            demand_trace_id=preference_trace_id,
            workforce_member_id=preference_member_id or member_id,
            operational_date=preference_date,
            evaluations=evaluations,
        ),
    )


def _ranked_ids(*items: WorkforceCandidateRankingInput) -> list[str]:
    return [
        item.workforce_member_id
        for item in rank_eligible_workforce_candidates(candidates=items)
    ]


def test_non_eligible_candidate_is_excluded():
    eligible = _input("eligible-member")
    excluded = _input("excluded-member", eligible=False)

    ranked = rank_eligible_workforce_candidates(
        candidates=(excluded, eligible)
    )

    assert [item.workforce_member_id for item in ranked] == [
        "eligible-member"
    ]


@pytest.mark.parametrize(
    ("first_outcome", "second_outcome"),
    (
        (
            PlanningPreferenceOutcome.PREFERRED,
            PlanningPreferenceOutcome.NEUTRAL,
        ),
        (
            PlanningPreferenceOutcome.NEUTRAL,
            PlanningPreferenceOutcome.DEPRIORITIZED,
        ),
    ),
)
def test_mandatory_outcome_order(first_outcome, second_outcome):
    first = _input("z-first", _preference("rule", 0, first_outcome))
    second = _input("a-second", _preference("rule", 0, second_outcome))

    assert _ranked_ids(second, first) == ["z-first", "a-second"]


def test_lower_priority_rule_dominates_higher_priority_rule():
    lower_priority_winner = _input(
        "z-lower-priority-winner",
        _preference("important", 0, PlanningPreferenceOutcome.PREFERRED),
        _preference("later", 10, PlanningPreferenceOutcome.DEPRIORITIZED),
    )
    higher_priority_winner = _input(
        "a-higher-priority-winner",
        _preference("important", 0, PlanningPreferenceOutcome.NEUTRAL),
        _preference("later", 10, PlanningPreferenceOutcome.PREFERRED),
    )

    assert _ranked_ids(higher_priority_winner, lower_priority_winner) == [
        "z-lower-priority-winner",
        "a-higher-priority-winner",
    ]


def test_complete_tie_uses_exact_external_identifier():
    second = _input("member-b")
    first = _input("member-A")

    assert _ranked_ids(second, first) == ["member-A", "member-b"]


def test_input_order_does_not_change_ranking():
    preferred = _input(
        "preferred",
        _preference("rule", 0, PlanningPreferenceOutcome.PREFERRED),
    )
    neutral = _input(
        "neutral",
        _preference("rule", 0, PlanningPreferenceOutcome.NEUTRAL),
    )

    assert _ranked_ids(preferred, neutral) == _ranked_ids(
        neutral,
        preferred,
    )


def test_missing_preference_is_neutral_in_key_without_mutating_source_set():
    preferred = _input(
        "preferred",
        _preference("rule", 0, PlanningPreferenceOutcome.PREFERRED),
    )
    missing = _input("missing")
    missing_before = missing.preference_set.model_dump(mode="json")

    ranked = rank_eligible_workforce_candidates(
        candidates=(missing, preferred)
    )
    missing_ranked = next(
        item for item in ranked if item.workforce_member_id == "missing"
    )

    assert [item.workforce_member_id for item in ranked] == [
        "preferred",
        "missing",
    ]
    assert missing_ranked.deterministic_priority.preference_entries == (
        PreferenceRankingKeyEntry(
            priority=0,
            code="rule",
            outcome=PlanningPreferenceOutcome.NEUTRAL,
        ),
    )
    assert missing.preference_set.model_dump(mode="json") == missing_before
    assert missing.preference_set.evaluations == ()


def test_duplicate_priority_and_code_is_rejected():
    duplicate = _preference("rule", 0, PlanningPreferenceOutcome.NEUTRAL)

    with pytest.raises(
        ValidationError,
        match="duplicate preference priority and code",
    ):
        _input("member", duplicate, duplicate)


def test_preference_set_member_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="preference set belongs"):
        _input("member-one", preference_member_id="member-two")


def test_preference_set_operational_date_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="operational date"):
        _input(
            "member-one",
            preference_date=date(2026, 8, 25),
        )


def test_eligibility_and_preference_trace_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="demand traces differ"):
        _input(
            "member-one",
            decision_trace_id="trace-one",
            preference_trace_id="trace-two",
        )


def test_ranked_candidate_propagates_validated_demand_trace():
    ranked = rank_eligible_workforce_candidates(
        candidates=(_input("member-one"),)
    )

    assert ranked[0].demand_trace_id == DEMAND_TRACE_ID


def test_rank_starts_at_one_and_is_sequential():
    ranked = rank_eligible_workforce_candidates(
        candidates=(
            _input("member-c"),
            _input("member-a"),
            _input("member-b"),
        )
    )

    assert [item.rank for item in ranked] == [1, 2, 3]


def test_deterministic_priority_is_structured_not_aggregated():
    item = _input(
        "member-one",
        _preference("rule-a", 0, PlanningPreferenceOutcome.PREFERRED),
        _preference("rule-b", 1, PlanningPreferenceOutcome.NEUTRAL),
    )

    ranked = rank_eligible_workforce_candidates(candidates=(item,))
    key = ranked[0].deterministic_priority

    assert isinstance(key, DeterministicCandidateRankingKey)
    assert [entry.code for entry in key.preference_entries] == [
        "rule-a",
        "rule-b",
    ]
    assert key.workforce_member_tie_breaker == "member-one"


def test_output_and_ranking_key_are_immutable():
    ranked = rank_eligible_workforce_candidates(
        candidates=(_input("member-one"),)
    )

    with pytest.raises(ValidationError):
        ranked[0].rank = 2
    with pytest.raises(ValidationError):
        ranked[0].deterministic_priority.workforce_member_tie_breaker = "other"
    with pytest.raises(TypeError):
        ranked[0].deterministic_priority.preference_entries[0] = None


def test_module_has_no_scoring_random_persistence_or_external_dependencies():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "candidate_ranking.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "float",
        "random",
        "created_at",
        "database",
        "repository",
        "sqlalchemy",
        "fastapi",
        "weighted",
        "average",
        "score",
        "sum(",
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WorkforceCandidateSnapshot,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    WorkforceEligibilityDecision,
)


_OUTCOME_ORDER = {
    PlanningPreferenceOutcome.PREFERRED: 0,
    PlanningPreferenceOutcome.NEUTRAL: 1,
    PlanningPreferenceOutcome.DEPRIORITIZED: 2,
}


class PreferenceRankingKeyEntry(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    priority: int = Field(ge=0, strict=True)
    code: str = Field(min_length=1)
    outcome: PlanningPreferenceOutcome


class DeterministicCandidateRankingKey(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    preference_entries: tuple[PreferenceRankingKeyEntry, ...] = Field(
        default_factory=tuple
    )
    workforce_member_tie_breaker: str = Field(min_length=1)


class WorkforceCandidateRankingInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate: WorkforceCandidateSnapshot
    eligibility_decision: WorkforceEligibilityDecision
    preference_set: WorkforcePlanningPreferenceSet

    @model_validator(mode="after")
    def validate_input_consistency(self) -> "WorkforceCandidateRankingInput":
        member_id = self.candidate.workforce_member_id
        if self.eligibility_decision.workforce_member_id != member_id:
            raise ValueError("eligibility decision belongs to another member")
        if self.preference_set.workforce_member_id != member_id:
            raise ValueError("preference set belongs to another member")
        if (
            self.preference_set.operational_date
            != self.eligibility_decision.operational_date
        ):
            raise ValueError(
                "preference set operational date does not match ranking context"
            )
        seen: set[tuple[int, str]] = set()
        for evaluation in self.preference_set.evaluations:
            identifier = (evaluation.priority, evaluation.code)
            if identifier in seen:
                raise ValueError(
                    "duplicate preference priority and code for candidate"
                )
            seen.add(identifier)
        return self


class RankedWorkforceCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    workforce_member_id: str = Field(min_length=1)
    rank: int = Field(ge=1, strict=True)
    candidate: WorkforceCandidateSnapshot
    eligibility_decision: WorkforceEligibilityDecision
    preference_set: WorkforcePlanningPreferenceSet
    deterministic_priority: DeterministicCandidateRankingKey


def _preference_universe(
    candidates: tuple[WorkforceCandidateRankingInput, ...],
) -> tuple[tuple[int, str], ...]:
    return tuple(
        sorted(
            {
                (evaluation.priority, evaluation.code)
                for item in candidates
                for evaluation in item.preference_set.evaluations
            }
        )
    )


def _deterministic_key(
    item: WorkforceCandidateRankingInput,
    universe: tuple[tuple[int, str], ...],
) -> DeterministicCandidateRankingKey:
    evaluations = {
        (evaluation.priority, evaluation.code): evaluation
        for evaluation in item.preference_set.evaluations
    }
    entries = tuple(
        PreferenceRankingKeyEntry(
            priority=priority,
            code=code,
            outcome=(
                evaluations[(priority, code)].outcome
                if (priority, code) in evaluations
                else PlanningPreferenceOutcome.NEUTRAL
            ),
        )
        for priority, code in universe
    )
    return DeterministicCandidateRankingKey(
        preference_entries=entries,
        workforce_member_tie_breaker=item.candidate.workforce_member_id,
    )


def _sort_key(
    deterministic_key: DeterministicCandidateRankingKey,
) -> tuple[tuple[int, ...], str]:
    return (
        tuple(
            _OUTCOME_ORDER[entry.outcome]
            for entry in deterministic_key.preference_entries
        ),
        deterministic_key.workforce_member_tie_breaker,
    )


def rank_eligible_workforce_candidates(
    *,
    candidates: tuple[WorkforceCandidateRankingInput, ...],
) -> tuple[RankedWorkforceCandidate, ...]:
    eligible_candidates = tuple(
        item for item in candidates if item.eligibility_decision.eligible
    )
    member_ids = [
        item.candidate.workforce_member_id for item in eligible_candidates
    ]
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("duplicate eligible workforce member in ranking input")

    universe = _preference_universe(eligible_candidates)
    candidates_with_keys = tuple(
        (item, _deterministic_key(item, universe))
        for item in eligible_candidates
    )
    ordered = tuple(
        sorted(
            candidates_with_keys,
            key=lambda pair: _sort_key(pair[1]),
        )
    )
    return tuple(
        RankedWorkforceCandidate(
            workforce_member_id=item.candidate.workforce_member_id,
            rank=rank,
            candidate=item.candidate,
            eligibility_decision=item.eligibility_decision,
            preference_set=item.preference_set,
            deterministic_priority=deterministic_key,
        )
        for rank, (item, deterministic_key) in enumerate(ordered, start=1)
    )

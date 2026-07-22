from app.domain.planning_readiness.models import (
    PlanningReadinessRuleResult,
    PlanningReadinessScore,
)


def calculate_planning_readiness_score(
    rule_results: tuple[PlanningReadinessRuleResult, ...],
) -> PlanningReadinessScore:
    total_weight = sum(item.weight for item in rule_results)
    if total_weight != 100:
        raise ValueError("Planning readiness rule weights must total 100.")
    earned_weight = sum(item.score_awarded for item in rule_results)
    return PlanningReadinessScore(
        value=round((earned_weight / total_weight) * 100),
        earned_weight=earned_weight,
        total_weight=total_weight,
    )

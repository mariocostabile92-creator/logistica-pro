from app.api.dependencies.planning_readiness import (
    get_planning_readiness_service,
)
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictEvaluator,
    PlanningConflictFormatter,
)
from app.runtime.planning_conflicts import PlanningConflictService


_conflict_service = PlanningConflictService(
    readiness_provider=get_planning_readiness_service(),
    engine=PlanningConflictEngine(
        PlanningConflictEvaluator(PlanningConflictFormatter())
    ),
)


def get_planning_conflict_service() -> PlanningConflictService:
    return _conflict_service

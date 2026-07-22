from app.api.dependencies.planning_conflicts import (
    get_planning_conflict_service,
)
from app.domain.planning_timeline import (
    PlanningTimelineEngine,
    PlanningTimelineFormatter,
)
from app.runtime.planning_timeline import PlanningTimelineRuntimeService


_timeline_service = PlanningTimelineRuntimeService(
    review_provider=get_planning_conflict_service(),
    engine=PlanningTimelineEngine(PlanningTimelineFormatter()),
)


def get_planning_timeline_service() -> PlanningTimelineRuntimeService:
    return _timeline_service

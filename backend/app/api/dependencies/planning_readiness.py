from datetime import timedelta

from app.domain.planning_readiness import PlanningReadinessEvaluator
from app.plugins.fleet.application.planning_input_producer import (
    produce_fleet_planning_input_snapshot,
)
from app.plugins.workforce.application.planning_input_producer import (
    produce_workforce_planning_input_snapshot,
)
from app.runtime.planning_inputs import PlanningInputRuntimeService
from app.runtime.planning_readiness import PlanningReadinessService


_DEFAULT_FRESHNESS_TTL = timedelta(hours=1)

_runtime_service = PlanningInputRuntimeService(
    workforce_producer=produce_workforce_planning_input_snapshot,
    fleet_producer=produce_fleet_planning_input_snapshot,
    workforce_freshness_ttl=_DEFAULT_FRESHNESS_TTL,
    fleet_freshness_ttl=_DEFAULT_FRESHNESS_TTL,
)
_readiness_service = PlanningReadinessService(
    composition_provider=_runtime_service,
    evaluator=PlanningReadinessEvaluator(),
)


def get_planning_readiness_service() -> PlanningReadinessService:
    return _readiness_service

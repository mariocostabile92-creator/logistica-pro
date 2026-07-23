from datetime import UTC, datetime

from app.domain.planning_runtime import (
    PlanningRuntimeOutputFormatter,
    PlanningRuntimeOutputValidator,
    PlanningRuntimeProducer,
    PlanningRuntimeProducerService,
)
from app.runtime.planning_output import (
    EmptyPlanningRuntimeProductionProvider,
    PlanningRuntimeOutputRuntime,
)


_clock = lambda: datetime.now(UTC)
_formatter = PlanningRuntimeOutputFormatter()
_producer_service = PlanningRuntimeProducerService(
    producer=PlanningRuntimeProducer(_formatter),
    validator=PlanningRuntimeOutputValidator(_formatter),
    formatter=_formatter,
)
_planning_runtime_output = PlanningRuntimeOutputRuntime(
    service=_producer_service,
    provider=EmptyPlanningRuntimeProductionProvider(),
    clock=_clock,
)


def get_planning_runtime_output() -> PlanningRuntimeOutputRuntime:
    return _planning_runtime_output

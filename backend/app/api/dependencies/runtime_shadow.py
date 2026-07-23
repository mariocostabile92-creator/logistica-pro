from datetime import UTC, datetime

from app.domain.runtime_shadow import PlanningComparator, RuntimeShadowService
from app.runtime.shadow import (
    EmptyRuntimeShadowResultProvider,
    RuntimeShadowRuntime,
)


_clock = lambda: datetime.now(UTC)
_runtime_shadow = RuntimeShadowRuntime(
    service=RuntimeShadowService(
        comparator=PlanningComparator(clock=_clock),
        clock=_clock,
    ),
    result_provider=EmptyRuntimeShadowResultProvider(),
    clock=_clock,
)


def get_runtime_shadow() -> RuntimeShadowRuntime:
    return _runtime_shadow

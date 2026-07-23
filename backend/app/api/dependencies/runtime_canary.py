from datetime import UTC, datetime

from app.domain.runtime_canary import (
    RuntimeCanaryPolicy,
    RuntimeCanaryService,
    RuntimeCanaryValidator,
)
from app.runtime.canary import (
    EmptyRuntimeCanaryContextProvider,
    RuntimeCanaryRuntime,
)


_clock = lambda: datetime.now(UTC)
_runtime_canary = RuntimeCanaryRuntime(
    service=RuntimeCanaryService(
        policy=RuntimeCanaryPolicy(),
        validator=RuntimeCanaryValidator(),
        clock=_clock,
    ),
    provider=EmptyRuntimeCanaryContextProvider(),
    clock=_clock,
)


def get_runtime_canary() -> RuntimeCanaryRuntime:
    return _runtime_canary

from datetime import UTC, datetime

from app.domain.runtime_primary import (
    RuntimePrimaryPolicy,
    RuntimePrimaryService,
    RuntimePrimaryValidator,
)
from app.runtime.primary import (
    BlockedLegacyFallback,
    BlockedRuntimePrimaryWriter,
    EmptyRuntimePrimaryContextProvider,
    RuntimePrimaryRuntime,
)


_clock = lambda: datetime.now(UTC)
_policy = RuntimePrimaryPolicy()
_runtime_primary = RuntimePrimaryRuntime(
    service=RuntimePrimaryService(
        validator=RuntimePrimaryValidator(_policy),
        writer=BlockedRuntimePrimaryWriter(),
        fallback=BlockedLegacyFallback(),
        clock=_clock,
    ),
    provider=EmptyRuntimePrimaryContextProvider(),
)


def get_runtime_primary() -> RuntimePrimaryRuntime:
    return _runtime_primary

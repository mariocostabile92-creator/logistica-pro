from datetime import UTC, datetime

from app.domain.legacy_retirement import (
    LegacyRetirementPolicy,
    LegacyRetirementService,
    LegacyRetirementValidator,
)
from app.runtime.legacy_retirement import (
    EmptyLegacyRetirementContextProvider,
    LegacyRetirementRuntime,
)


_clock = lambda: datetime.now(UTC)
_policy = LegacyRetirementPolicy()
_legacy_retirement = LegacyRetirementRuntime(
    service=LegacyRetirementService(
        validator=LegacyRetirementValidator(_policy),
        clock=_clock,
    ),
    provider=EmptyLegacyRetirementContextProvider(),
)


def get_legacy_retirement() -> LegacyRetirementRuntime:
    return _legacy_retirement

from typing import Protocol

from app.domain.legacy_retirement import (
    LegacyRetirementContext,
    LegacyRetirementScope,
)


class LegacyRetirementContextProvider(Protocol):
    def get(
        self,
        *,
        scope: LegacyRetirementScope,
    ) -> LegacyRetirementContext | None: ...


class EmptyLegacyRetirementContextProvider:
    def get(
        self,
        *,
        scope: LegacyRetirementScope,
    ) -> LegacyRetirementContext | None:
        return None

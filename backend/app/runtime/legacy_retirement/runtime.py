from app.domain.legacy_retirement import (
    LegacyRetirementReport,
    LegacyRetirementScope,
    LegacyRetirementService,
)
from app.runtime.legacy_retirement.contracts import (
    LegacyRetirementContextProvider,
)


class LegacyRetirementRuntime:
    def __init__(
        self,
        *,
        service: LegacyRetirementService,
        provider: LegacyRetirementContextProvider,
    ) -> None:
        self._service = service
        self._provider = provider

    def current(
        self,
        *,
        scope: LegacyRetirementScope,
    ) -> LegacyRetirementReport:
        context = self._provider.get(scope=scope)
        if context is None:
            return self._service.unavailable(
                scope=scope,
                code="LEGACY_RETIREMENT_CERTIFICATION_NO_GO",
                message=(
                    "Legacy Retirement non autorizzato: certificazione "
                    "corrente Level 0 / NO-GO."
                ),
            )
        if context.scope != scope:
            return self._service.unavailable(
                scope=scope,
                code="LEGACY_RETIREMENT_SCOPE_MISMATCH",
                message=(
                    "Il contesto Legacy Retirement non appartiene "
                    "all'organizzazione richiesta."
                ),
            )
        return self._service.assess(context)

    def observe(
        self,
        *,
        scope: LegacyRetirementScope,
    ) -> LegacyRetirementReport:
        context = self._provider.get(scope=scope)
        if context is None or context.scope != scope:
            return self.current(scope=scope)
        return self._service.observe(context)

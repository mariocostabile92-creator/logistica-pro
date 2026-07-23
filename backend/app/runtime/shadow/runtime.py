from collections.abc import Callable
from datetime import datetime

from app.domain.execution_attempt import ExecutionAttempt
from app.domain.execution_intent import ExecutionIntent
from app.domain.runtime_authority import AuthorityResolutionResult
from app.domain.runtime_shadow import (
    RuntimeShadowDiagnostic,
    RuntimeShadowDiagnostics,
    RuntimeShadowDiagnosticSeverity,
    RuntimeShadowResult,
    RuntimeShadowScope,
    RuntimeShadowService,
    RuntimeShadowSnapshot,
    RuntimeShadowState,
)
from app.runtime.shadow.contracts import RuntimeShadowResultProvider


class RuntimeShadowRuntime:
    def __init__(
        self,
        *,
        service: RuntimeShadowService,
        result_provider: RuntimeShadowResultProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._result_provider = result_provider
        self._clock = clock

    def current(
        self,
        *,
        scope: RuntimeShadowScope,
        publication_version: int,
    ) -> RuntimeShadowResult:
        result = self._result_provider.get(
            scope=scope,
            publication_version=publication_version,
        )
        if result is not None:
            return result

        generated_at = self._clock()
        return RuntimeShadowResult(
            state=RuntimeShadowState.NOT_AVAILABLE,
            diagnostics=RuntimeShadowDiagnostics(
                items=(
                    RuntimeShadowDiagnostic(
                        code="SHADOW_RESULT_NOT_AVAILABLE",
                        severity=RuntimeShadowDiagnosticSeverity.INFO,
                        message=(
                            "Nessun confronto Shadow disponibile per lo scope; "
                            "nessun effetto operativo applicato."
                        ),
                    ),
                ),
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    def compare(
        self,
        *,
        legacy: RuntimeShadowSnapshot,
        runtime: RuntimeShadowSnapshot,
        authority: AuthorityResolutionResult,
        intent: ExecutionIntent,
        attempt: ExecutionAttempt | None,
    ) -> RuntimeShadowResult:
        return self._service.compare(
            legacy=legacy,
            runtime=runtime,
            authority=authority,
            intent=intent,
            attempt=attempt,
        )

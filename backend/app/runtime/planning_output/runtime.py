from collections.abc import Callable
from datetime import datetime

from app.domain.planning_runtime import (
    PlanningRuntimeDiagnosticSeverity,
    PlanningRuntimeOutputDiagnostic,
    PlanningRuntimeOutputDiagnostics,
    PlanningRuntimeOutputStatus,
    PlanningRuntimeProducerResult,
    PlanningRuntimeProducerService,
    PlanningRuntimeProductionContext,
    PlanningRuntimeScope,
)
from app.runtime.planning_output.contracts import (
    PlanningRuntimeProductionProvider,
)


class PlanningRuntimeOutputRuntime:
    def __init__(
        self,
        *,
        service: PlanningRuntimeProducerService,
        provider: PlanningRuntimeProductionProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._provider = provider
        self._clock = clock

    def current(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> PlanningRuntimeProducerResult:
        context = self._provider.get(
            scope=scope,
            publication_id=publication_id,
            publication_version=publication_version,
        )
        if context is None:
            generated_at = self._clock()
            return PlanningRuntimeProducerResult(
                status=PlanningRuntimeOutputStatus.NOT_AVAILABLE,
                diagnostics=PlanningRuntimeOutputDiagnostics(
                    valid=False,
                    items=(
                        PlanningRuntimeOutputDiagnostic(
                            code="RUNTIME_SOURCE_NOT_AVAILABLE",
                            severity=PlanningRuntimeDiagnosticSeverity.ERROR,
                            message=(
                                "Published Plan privo di payload operativo "
                                "completo e immutabile."
                            ),
                        ),
                    ),
                    generated_at=generated_at,
                ),
                generated_at=generated_at,
            )
        source = context.source
        if (
            source.scope != scope
            or source.publication.publication_id != publication_id
            or source.publication.publication_version != publication_version
        ):
            generated_at = self._clock()
            return PlanningRuntimeProducerResult(
                status=PlanningRuntimeOutputStatus.REJECTED,
                diagnostics=PlanningRuntimeOutputDiagnostics(
                    valid=False,
                    items=(
                        PlanningRuntimeOutputDiagnostic(
                            code="RUNTIME_REQUEST_SCOPE_MISMATCH",
                            severity=PlanningRuntimeDiagnosticSeverity.ERROR,
                            message=(
                                "Il payload Runtime non appartiene allo "
                                "scope o alla Publication richiesta."
                            ),
                        ),
                    ),
                    generated_at=generated_at,
                ),
                generated_at=generated_at,
            )
        return self.produce(context)

    def produce(
        self,
        context: PlanningRuntimeProductionContext,
    ) -> PlanningRuntimeProducerResult:
        return self._service.produce(context)

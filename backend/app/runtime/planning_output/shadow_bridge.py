from pydantic import BaseModel, ConfigDict

from app.domain.planning_runtime import (
    PlanningRuntimeOutputFormatter,
    PlanningRuntimeOutput,
    PlanningRuntimeProducerResult,
    PlanningRuntimeProducerService,
    PlanningRuntimeProductionContext,
)
from app.domain.runtime_shadow import (
    RuntimeShadowPublication,
    RuntimeShadowResult,
    RuntimeShadowService,
    RuntimeShadowSnapshot,
    RuntimeShadowSource,
)


class PlanningRuntimeComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    producer: PlanningRuntimeProducerResult
    shadow: RuntimeShadowResult | None = None


class PlanningRuntimeShadowBridge:
    def __init__(
        self,
        *,
        producer_service: PlanningRuntimeProducerService,
        shadow_service: RuntimeShadowService,
        formatter: PlanningRuntimeOutputFormatter,
    ) -> None:
        self._producer_service = producer_service
        self._shadow_service = shadow_service
        self._formatter = formatter

    def compare(
        self,
        *,
        context: PlanningRuntimeProductionContext,
        legacy: RuntimeShadowSnapshot,
    ) -> PlanningRuntimeComparisonResult:
        produced = self._producer_service.produce(context)
        if produced.snapshot is None:
            return PlanningRuntimeComparisonResult(producer=produced)

        runtime = self._runtime_snapshot(produced.snapshot.output)
        shadow = self._shadow_service.compare(
            legacy=legacy,
            runtime=runtime,
            authority=context.authority,
            intent=context.intent,
            attempt=context.attempt,
        )
        if produced.metrics is not None and shadow.report is not None:
            produced = produced.model_copy(
                update={
                    "metrics": produced.metrics.model_copy(
                        update={
                            "parity_percent": shadow.report.parity_percent,
                        }
                    )
                }
            )
        return PlanningRuntimeComparisonResult(
            producer=produced,
            shadow=shadow,
        )

    def _runtime_snapshot(
        self,
        output: PlanningRuntimeOutput,
    ) -> RuntimeShadowSnapshot:
        return RuntimeShadowSnapshot(
            source=RuntimeShadowSource.RUNTIME,
            scope=output.scope.model_dump(mode="json"),
            publication=RuntimeShadowPublication(
                publication_id=output.metadata.publication_id,
                publication_version=output.publication_version,
            ),
            planning_version=output.planning_version,
            resources=self._formatter.resources(output),
            fleet=self._formatter.fleet(output),
            assignments=self._formatter.assignments(output),
            capabilities=self._formatter.capabilities(output),
            availability=self._formatter.availability(output),
            fingerprint=output.fingerprint,
            input_fingerprint=output.metadata.input_fingerprint,
            configuration_version=output.metadata.configuration_version,
            rules_version=output.metadata.rules_version,
            validation_errors=(),
            evaluation_at=output.metadata.generated_at,
            generated_at=output.metadata.generated_at,
        )

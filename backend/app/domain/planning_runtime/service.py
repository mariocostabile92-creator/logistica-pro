from collections.abc import Callable
from time import perf_counter

from app.domain.planning_runtime.formatter import PlanningRuntimeOutputFormatter
from app.domain.planning_runtime.models import (
    PlanningRuntimeDiagnosticSeverity,
    PlanningRuntimeOutputDiagnostic,
    PlanningRuntimeOutputDiagnostics,
    PlanningRuntimeOutputStatus,
    PlanningRuntimeProducerMetrics,
    PlanningRuntimeProducerResult,
    PlanningRuntimeProductionContext,
    PlanningRuntimeSnapshot,
)
from app.domain.planning_runtime.producer import PlanningRuntimeProducer
from app.domain.planning_runtime.validator import PlanningRuntimeOutputValidator


class PlanningRuntimeProducerService:
    def __init__(
        self,
        *,
        producer: PlanningRuntimeProducer,
        validator: PlanningRuntimeOutputValidator,
        formatter: PlanningRuntimeOutputFormatter,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._producer = producer
        self._validator = validator
        self._formatter = formatter
        self._timer = timer

    def produce(
        self,
        context: PlanningRuntimeProductionContext,
    ) -> PlanningRuntimeProducerResult:
        started = self._timer()
        diagnostics = self._validator.validate_context(context)
        if not diagnostics.valid:
            return PlanningRuntimeProducerResult(
                status=PlanningRuntimeOutputStatus.REJECTED,
                diagnostics=diagnostics,
                generated_at=context.source.evaluation_at,
            )

        generation_started = self._timer()
        try:
            output = self._producer.produce(context.source)
        except Exception:
            failure = PlanningRuntimeOutputDiagnostics(
                valid=False,
                items=(
                    PlanningRuntimeOutputDiagnostic(
                        code="RUNTIME_OUTPUT_GENERATION_FAILED",
                        severity=PlanningRuntimeDiagnosticSeverity.ERROR,
                        message=(
                            "Runtime Producer non ha generato alcun output."
                        ),
                    ),
                ),
                generated_at=context.source.evaluation_at,
            )
            return PlanningRuntimeProducerResult(
                status=PlanningRuntimeOutputStatus.REJECTED,
                diagnostics=failure,
                generated_at=context.source.evaluation_at,
            )
        generation_time_ms = max(
            0.0,
            (self._timer() - generation_started) * 1_000,
        )
        output_diagnostics = self._validator.validate_output(output)
        if not output_diagnostics.valid:
            return PlanningRuntimeProducerResult(
                status=PlanningRuntimeOutputStatus.REJECTED,
                diagnostics=output_diagnostics,
                generated_at=context.source.evaluation_at,
            )

        snapshot_size = self._formatter.snapshot_size(output)
        snapshot = PlanningRuntimeSnapshot(
            snapshot_id=f"runtime-output-{output.fingerprint[:32]}",
            output=output,
            snapshot_size_bytes=snapshot_size,
        )
        producer_latency_ms = max(0.0, (self._timer() - started) * 1_000)
        combined_diagnostics = PlanningRuntimeOutputDiagnostics(
            valid=True,
            items=diagnostics.items + output_diagnostics.items,
            generated_at=context.source.evaluation_at,
        )
        return PlanningRuntimeProducerResult(
            status=PlanningRuntimeOutputStatus.READY,
            snapshot=snapshot,
            metrics=PlanningRuntimeProducerMetrics(
                producer_latency_ms=producer_latency_ms,
                generation_time_ms=generation_time_ms,
                snapshot_size_bytes=snapshot_size,
            ),
            diagnostics=combined_diagnostics,
            generated_at=context.source.evaluation_at,
        )

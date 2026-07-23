from collections.abc import Callable
from datetime import datetime

from app.domain.runtime_canary.metrics import (
    calculate_canary_metrics,
    evaluate_canary_criteria,
)
from app.domain.runtime_canary.models import (
    RuntimeCanaryDecision,
    RuntimeCanaryDiagnostic,
    RuntimeCanaryDiagnostics,
    RuntimeCanaryDiagnosticSeverity,
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryMetrics,
    RuntimeCanaryPolicy,
    RuntimeCanaryReport,
    RuntimeCanaryResult,
    RuntimeCanarySession,
    RuntimeCanaryStatus,
)
from app.domain.runtime_canary.validator import RuntimeCanaryValidator


class RuntimeCanaryService:
    def __init__(
        self,
        *,
        policy: RuntimeCanaryPolicy,
        validator: RuntimeCanaryValidator,
        clock: Callable[[], datetime],
    ) -> None:
        self._policy = policy
        self._validator = validator
        self._clock = clock

    def evaluate(
        self,
        context: RuntimeCanaryEvaluationContext,
    ) -> RuntimeCanaryResult:
        try:
            diagnostics = self._validator.validate(context)
            prerequisites_valid = not any(
                item.severity is RuntimeCanaryDiagnosticSeverity.ERROR
                for item in diagnostics.items
            )
            if not prerequisites_valid:
                return self._complete(
                    context=context,
                    terminal_status=RuntimeCanaryStatus.ABORTED,
                    diagnostics=diagnostics,
                    prerequisites_valid=False,
                    status_history=(
                        RuntimeCanaryStatus.CREATED,
                        RuntimeCanaryStatus.RUNNING,
                        RuntimeCanaryStatus.ABORTED,
                    ),
                )
            return self._complete(
                context=context,
                terminal_status=RuntimeCanaryStatus.FINISHED,
                diagnostics=diagnostics,
                prerequisites_valid=True,
                status_history=(
                    RuntimeCanaryStatus.CREATED,
                    RuntimeCanaryStatus.RUNNING,
                    RuntimeCanaryStatus.OBSERVING,
                    RuntimeCanaryStatus.FINISHED,
                ),
            )
        except Exception:
            return self._failed(context)

    def unavailable(
        self,
        *,
        session: RuntimeCanarySession,
        code: str,
        message: str,
    ) -> RuntimeCanaryResult:
        diagnostics = RuntimeCanaryDiagnostics(
            items=(
                RuntimeCanaryDiagnostic(
                    code=code,
                    severity=RuntimeCanaryDiagnosticSeverity.ERROR,
                    message=message,
                ),
            ),
            generated_at=session.started_at,
        )
        return self._empty_result(
            session=session,
            status=RuntimeCanaryStatus.ABORTED,
            diagnostics=diagnostics,
            history=(
                RuntimeCanaryStatus.CREATED,
                RuntimeCanaryStatus.RUNNING,
                RuntimeCanaryStatus.ABORTED,
            ),
        )

    def _complete(
        self,
        *,
        context: RuntimeCanaryEvaluationContext,
        terminal_status: RuntimeCanaryStatus,
        diagnostics: RuntimeCanaryDiagnostics,
        prerequisites_valid: bool,
        status_history: tuple[RuntimeCanaryStatus, ...],
    ) -> RuntimeCanaryResult:
        ended_at = self._end_time(context.session.started_at)
        session = self._terminal_session(
            context.session,
            status=terminal_status,
            ended_at=ended_at,
        )
        metrics = calculate_canary_metrics(context)
        performance_diagnostics: tuple[RuntimeCanaryDiagnostic, ...] = ()
        if (
            metrics.canary_overhead_percent is not None
            and metrics.canary_overhead_percent
            > self._policy.maximum_canary_overhead_percent
        ):
            performance_diagnostics = (
                RuntimeCanaryDiagnostic(
                    code="CANARY_OVERHEAD_TARGET_EXCEEDED",
                    severity=RuntimeCanaryDiagnosticSeverity.WARNING,
                    message=(
                        "Overhead Canary oltre il target; la decisione resta "
                        "informativa e Runtime resta osservatore."
                    ),
                ),
            )
        criteria = evaluate_canary_criteria(
            metrics,
            policy=self._policy,
            prerequisites_valid=prerequisites_valid,
        )
        decision = (
            RuntimeCanaryDecision.PASS
            if all(item.passed for item in criteria)
            else RuntimeCanaryDecision.FAIL
        )
        outcome_diagnostic = RuntimeCanaryDiagnostic(
            code=f"CANARY_{decision.value}",
            severity=(
                RuntimeCanaryDiagnosticSeverity.INFO
                if decision is RuntimeCanaryDecision.PASS
                else RuntimeCanaryDiagnosticSeverity.WARNING
            ),
            message=(
                "Criteri Canary soddisfatti; nessuna promozione automatica."
                if decision is RuntimeCanaryDecision.PASS
                else "Criteri Canary non soddisfatti; Runtime resta osservatore."
            ),
        )
        report_diagnostics = RuntimeCanaryDiagnostics(
            items=(
                diagnostics.items
                + performance_diagnostics
                + (outcome_diagnostic,)
            ),
            generated_at=ended_at,
        )
        shadow = context.shadow_result
        mismatches = shadow.mismatches if shadow is not None else ()
        return RuntimeCanaryResult(
            session=session,
            report=RuntimeCanaryReport(
                summary=(
                    "Canary completato in sola osservazione."
                    if terminal_status is RuntimeCanaryStatus.FINISHED
                    else "Canary interrotto in modalita fail-closed."
                ),
                metrics=metrics,
                mismatches=mismatches,
                diagnostics=report_diagnostics,
                duration_ms=self._duration_ms(
                    session.started_at,
                    ended_at,
                ),
                decision=decision,
                criteria=criteria,
                generated_at=ended_at,
            ),
            status_history=status_history,
        )

    def _failed(
        self,
        context: RuntimeCanaryEvaluationContext,
    ) -> RuntimeCanaryResult:
        diagnostics = RuntimeCanaryDiagnostics(
            items=(
                RuntimeCanaryDiagnostic(
                    code="CANARY_EVALUATION_FAILED",
                    severity=RuntimeCanaryDiagnosticSeverity.ERROR,
                    message=(
                        "Valutazione Canary fallita; Runtime resta osservatore."
                    ),
                ),
            ),
            generated_at=context.session.started_at,
        )
        return self._empty_result(
            session=context.session,
            status=RuntimeCanaryStatus.ABORTED,
            diagnostics=diagnostics,
            history=(
                RuntimeCanaryStatus.CREATED,
                RuntimeCanaryStatus.RUNNING,
                RuntimeCanaryStatus.ABORTED,
            ),
        )

    def _empty_result(
        self,
        *,
        session: RuntimeCanarySession,
        status: RuntimeCanaryStatus,
        diagnostics: RuntimeCanaryDiagnostics,
        history: tuple[RuntimeCanaryStatus, ...],
    ) -> RuntimeCanaryResult:
        ended_at = self._end_time(session.started_at)
        terminal_session = self._terminal_session(
            session,
            status=status,
            ended_at=ended_at,
        )
        metrics = RuntimeCanaryMetrics(
            parity_percent=0,
            critical_mismatch=0,
            high_mismatch=0,
            medium_mismatch=0,
            low_mismatch=0,
            duplicate_execution=0,
            authority_conflict=0,
            shadow_latency_ms=0,
            producer_latency_ms=0,
            comparator_latency_ms=0,
        )
        criteria = evaluate_canary_criteria(
            metrics,
            policy=self._policy,
            prerequisites_valid=False,
        )
        return RuntimeCanaryResult(
            session=terminal_session,
            report=RuntimeCanaryReport(
                summary="Canary non eseguito; Runtime resta osservatore.",
                metrics=metrics,
                diagnostics=diagnostics,
                duration_ms=self._duration_ms(session.started_at, ended_at),
                decision=RuntimeCanaryDecision.FAIL,
                criteria=criteria,
                generated_at=ended_at,
            ),
            status_history=history,
        )

    def _end_time(self, started_at: datetime) -> datetime:
        current = self._clock()
        return current if current >= started_at else started_at

    @staticmethod
    def _duration_ms(started_at: datetime, ended_at: datetime) -> float:
        return max(0.0, (ended_at - started_at).total_seconds() * 1_000)

    @staticmethod
    def _terminal_session(
        session: RuntimeCanarySession,
        *,
        status: RuntimeCanaryStatus,
        ended_at: datetime,
    ) -> RuntimeCanarySession:
        return RuntimeCanarySession.model_validate(
            {
                **session.model_dump(mode="python"),
                "status": status,
                "ended_at": ended_at,
            }
        )

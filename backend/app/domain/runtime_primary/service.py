from collections.abc import Callable
from datetime import datetime
from time import perf_counter

from app.domain.planning_runtime import PlanningRuntimeScope
from app.domain.runtime_primary.diagnostics import (
    RuntimePrimaryDiagnosticsBuilder,
)
from app.domain.runtime_primary.models import (
    RuntimePrimaryDecision,
    RuntimePrimaryDiagnosticSeverity,
    RuntimePrimaryDiagnostics,
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryMetrics,
    RuntimePrimaryMode,
    RuntimePrimaryOutcome,
    RuntimePrimaryReport,
    RuntimePrimaryStatus,
    RuntimePrimaryValidationResult,
    RuntimePrimaryValidationRule,
)
from app.domain.runtime_primary.ports import (
    LegacyFallback,
    RuntimePrimaryWriter,
)
from app.domain.runtime_primary.validator import RuntimePrimaryValidator


class RuntimePrimaryService:
    def __init__(
        self,
        *,
        validator: RuntimePrimaryValidator,
        writer: RuntimePrimaryWriter,
        fallback: LegacyFallback,
        clock: Callable[[], datetime],
    ) -> None:
        self._validator = validator
        self._writer = writer
        self._fallback = fallback
        self._clock = clock

    def assess(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryReport:
        started = perf_counter()
        validation_started = perf_counter()
        validation = self._validator.validate(context)
        validation_ms = (perf_counter() - validation_started) * 1_000
        diagnostics = RuntimePrimaryDiagnosticsBuilder.from_validation(
            validation
        )
        if not validation.allowed:
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=(
                    RuntimePrimaryStatus.DISABLED
                    if context.requested_mode is RuntimePrimaryMode.DISABLED
                    else RuntimePrimaryStatus.REJECTED
                ),
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.FAILED_CLOSED,
                reason="Promozione negata in modalita fail-closed.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
            )
        if context.requested_mode is RuntimePrimaryMode.CANARY:
            status = RuntimePrimaryStatus.CANARY
            decision = RuntimePrimaryDecision.OBSERVE
            reason = "Runtime limitato alla coorte Canary senza scritture."
        elif context.requested_mode is RuntimePrimaryMode.ROLLBACK:
            status = RuntimePrimaryStatus.READY_TO_ROLLBACK
            decision = RuntimePrimaryDecision.ELIGIBLE
            reason = "Rollback validato; nessun fallback eseguito dalla query."
        else:
            status = RuntimePrimaryStatus.READY_TO_PROMOTE
            decision = RuntimePrimaryDecision.ELIGIBLE
            reason = "Promozione valida; nessuna scrittura eseguita dalla query."
        return self._report(
            context=context,
            validation=validation,
            diagnostics=diagnostics,
            status=status,
            decision=decision,
            outcome=RuntimePrimaryOutcome.NO_EFFECT,
            reason=reason,
            validation_ms=validation_ms,
            total_ms=(perf_counter() - started) * 1_000,
        )

    def apply(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryReport:
        if context.requested_mode is RuntimePrimaryMode.PRIMARY:
            return self._promote(context)
        if context.requested_mode is RuntimePrimaryMode.ROLLBACK:
            return self._rollback(context)
        return self.assess(context)

    def unavailable(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
        code: str,
        message: str,
    ) -> RuntimePrimaryReport:
        generated_at = self._clock()
        validation = RuntimePrimaryValidationResult(
            allowed=False,
            rules=(
                RuntimePrimaryValidationRule(
                    code=code,
                    passed=False,
                    reason=message,
                    remediation_hint=(
                        "Mantenere il Legacy come unico writer finche tutti "
                        "i gate obbligatori non risultano PASS."
                    ),
                ),
            ),
            evaluated_at=generated_at,
        )
        diagnostics = RuntimePrimaryDiagnosticsBuilder.from_validation(
            validation
        )
        status = RuntimePrimaryStatus.DISABLED
        return RuntimePrimaryReport(
            scope=scope,
            publication_id=publication_id,
            publication_version=publication_version,
            mode=RuntimePrimaryMode.DISABLED,
            status=status,
            decision=RuntimePrimaryDecision.DENY,
            reason=message,
            validation=validation,
            metrics=RuntimePrimaryMetrics(
                promotion_status=status,
            ),
            diagnostics=diagnostics,
            duration_ms=0,
            outcome=RuntimePrimaryOutcome.FAILED_CLOSED,
            generated_at=generated_at,
        )

    def _promote(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryReport:
        started = perf_counter()
        validation_started = perf_counter()
        validation = self._validator.validate(context)
        validation_ms = (perf_counter() - validation_started) * 1_000
        diagnostics = RuntimePrimaryDiagnosticsBuilder.from_validation(
            validation
        )
        if not validation.allowed:
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.REJECTED,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.FAILED_CLOSED,
                reason="Runtime non promosso: precondizioni non soddisfatte.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
            )
        try:
            result = self._writer.write(context)
        except Exception:
            diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
                diagnostics,
                code="RUNTIME_PRIMARY_WRITE_FAILED",
                severity=RuntimePrimaryDiagnosticSeverity.ERROR,
                message=(
                    "Scrittura Runtime fallita; nessun fallback automatico."
                ),
                remediation_hint=(
                    "Bloccare lo scope e avviare reconciliation."
                ),
            )
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.ERROR,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.ERROR,
                reason="Scrittura Runtime fallita in modalita fail-closed.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
            )
        result_valid = (
            result.committed
            and result.runtime_write_count == 1
            and result.duplicate_execution == 0
            and result.fencing_token
            == context.intent.fencing_token
        )
        if not result_valid:
            diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
                diagnostics,
                code="RUNTIME_PRIMARY_WRITE_INVARIANT_FAILED",
                severity=RuntimePrimaryDiagnosticSeverity.ERROR,
                message="Esito writer non coerente con single-writer.",
                remediation_hint=(
                    "Arrestare la coorte e riconciliare l'esecuzione."
                ),
            )
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.ERROR,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.ERROR,
                reason="Invariante di scrittura Runtime violata.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
                runtime_write_count=result.runtime_write_count,
                duplicate_execution=result.duplicate_execution,
                write_latency_ms=result.latency_ms,
            )
        diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
            diagnostics,
            code="RUNTIME_PRIMARY_PROMOTED",
            severity=RuntimePrimaryDiagnosticSeverity.INFO,
            message="Runtime promosso per la sola coorte autorizzata.",
        )
        return self._report(
            context=context,
            validation=validation,
            diagnostics=diagnostics,
            status=RuntimePrimaryStatus.PRIMARY,
            decision=RuntimePrimaryDecision.PROMOTED,
            outcome=RuntimePrimaryOutcome.RUNTIME_WRITE_COMMITTED,
            reason="Runtime Primary attivo sullo scope autorizzato.",
            validation_ms=validation_ms,
            total_ms=(perf_counter() - started) * 1_000,
            runtime_write_count=1,
            write_latency_ms=result.latency_ms,
        )

    def _rollback(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryReport:
        started = perf_counter()
        validation_started = perf_counter()
        validation = self._validator.validate(context)
        validation_ms = (perf_counter() - validation_started) * 1_000
        diagnostics = RuntimePrimaryDiagnosticsBuilder.from_validation(
            validation
        )
        if not validation.allowed:
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.REJECTED,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.FAILED_CLOSED,
                reason="Rollback negato: reconciliation o Authority mancanti.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
            )
        try:
            result = self._fallback.activate(context)
        except Exception:
            diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
                diagnostics,
                code="LEGACY_FALLBACK_FAILED",
                severity=RuntimePrimaryDiagnosticSeverity.ERROR,
                message="Attivazione Legacy fallita.",
                remediation_hint=(
                    "Mantenere lo scope bloccato e proseguire il recovery."
                ),
            )
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.ERROR,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.ERROR,
                reason="Fallback Legacy fallito.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
            )
        fallback_valid = (
            result.activated
            and result.legacy_fallback_count == 1
            and result.state_preserved
        )
        if not fallback_valid:
            diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
                diagnostics,
                code="LEGACY_FALLBACK_INVARIANT_FAILED",
                severity=RuntimePrimaryDiagnosticSeverity.ERROR,
                message="Fallback Legacy privo di stato verificato.",
                remediation_hint=(
                    "Bloccare lo scope e ripetere la reconciliation."
                ),
            )
            return self._report(
                context=context,
                validation=validation,
                diagnostics=diagnostics,
                status=RuntimePrimaryStatus.ERROR,
                decision=RuntimePrimaryDecision.DENY,
                outcome=RuntimePrimaryOutcome.ERROR,
                reason="Invariante fallback Legacy violata.",
                validation_ms=validation_ms,
                total_ms=(perf_counter() - started) * 1_000,
                legacy_fallback_count=result.legacy_fallback_count,
                fallback_latency_ms=result.latency_ms,
            )
        diagnostics = RuntimePrimaryDiagnosticsBuilder.append(
            diagnostics,
            code="LEGACY_FALLBACK_ACTIVATED",
            severity=RuntimePrimaryDiagnosticSeverity.INFO,
            message="Legacy riattivato sul solo scope riconciliato.",
        )
        return self._report(
            context=context,
            validation=validation,
            diagnostics=diagnostics,
            status=RuntimePrimaryStatus.ROLLED_BACK,
            decision=RuntimePrimaryDecision.FALLBACK,
            outcome=RuntimePrimaryOutcome.LEGACY_FALLBACK_ACTIVATED,
            reason="Rollback completato senza perdita di stato.",
            validation_ms=validation_ms,
            total_ms=(perf_counter() - started) * 1_000,
            legacy_fallback_count=1,
            rollback_count=1,
            fallback_latency_ms=result.latency_ms,
        )

    def _report(
        self,
        *,
        context: RuntimePrimaryEvaluationContext,
        validation: RuntimePrimaryValidationResult,
        diagnostics: RuntimePrimaryDiagnostics,
        status: RuntimePrimaryStatus,
        decision: RuntimePrimaryDecision,
        outcome: RuntimePrimaryOutcome,
        reason: str,
        validation_ms: float,
        total_ms: float,
        runtime_write_count: int = 0,
        legacy_fallback_count: int = 0,
        duplicate_execution: int | None = None,
        rollback_count: int = 0,
        write_latency_ms: float = 0,
        fallback_latency_ms: float = 0,
    ) -> RuntimePrimaryReport:
        canary_metrics = (
            context.canary.report.metrics if context.canary else None
        )
        parity = canary_metrics.parity_percent if canary_metrics else 0
        critical = (
            canary_metrics.critical_mismatch if canary_metrics else 0
        )
        duplicates = (
            duplicate_execution
            if duplicate_execution is not None
            else (
                canary_metrics.duplicate_execution
                if canary_metrics
                else 0
            )
        )
        throughput = (
            runtime_write_count / (total_ms / 1_000)
            if runtime_write_count and total_ms > 0
            else None
        )
        overhead = None
        if context.legacy_latency_ms is not None:
            overhead = (
                total_ms / context.legacy_latency_ms * 100
            )
        generated_at = self._clock()
        return RuntimePrimaryReport(
            scope=context.scope,
            publication_id=context.publication.publication_id,
            publication_version=context.publication.publication_version,
            mode=context.requested_mode,
            status=status,
            decision=decision,
            reason=reason,
            validation=validation,
            metrics=RuntimePrimaryMetrics(
                runtime_write_count=runtime_write_count,
                legacy_fallback_count=legacy_fallback_count,
                parity_percent=parity,
                critical_mismatch=critical,
                duplicate_execution=duplicates,
                rollback_count=rollback_count,
                canary_observation_days=(
                    context.cohort_evidence.observed_operational_days
                ),
                canary_execution_count=(
                    context.cohort_evidence.observed_execution_count
                ),
                execution_success_percent=(
                    context.cohort_evidence.execution_success_percent
                ),
                promotion_status=status,
                validation_latency_ms=validation_ms,
                write_latency_ms=write_latency_ms,
                fallback_latency_ms=fallback_latency_ms,
                total_latency_ms=total_ms,
                throughput_per_second=throughput,
                overhead_percent=overhead,
            ),
            diagnostics=RuntimePrimaryDiagnostics(
                items=diagnostics.items,
                generated_at=generated_at,
            ),
            duration_ms=total_ms,
            outcome=outcome,
            generated_at=generated_at,
        )

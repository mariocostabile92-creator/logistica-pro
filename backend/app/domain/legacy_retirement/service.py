from collections.abc import Callable
from datetime import datetime
from time import perf_counter

from app.domain.legacy_retirement.diagnostics import (
    LegacyRetirementDiagnosticsBuilder,
)
from app.domain.legacy_retirement.models import (
    LegacyRetirementBlocker,
    LegacyRetirementBlockerSeverity,
    LegacyRetirementCheck,
    LegacyRetirementContext,
    LegacyRetirementDiagnostics,
    LegacyRetirementGateSummary,
    LegacyRetirementMetrics,
    LegacyRetirementReport,
    LegacyRetirementScope,
    LegacyRetirementState,
    LegacyRetirementValidationResult,
)
from app.domain.legacy_retirement.validator import (
    LegacyRetirementValidator,
)
from app.domain.runtime_primary import (
    RuntimeCertificationGateStatus,
    RuntimeCertificationLevel,
)


class LegacyRetirementService:
    def __init__(
        self,
        *,
        validator: LegacyRetirementValidator,
        clock: Callable[[], datetime],
    ) -> None:
        self._validator = validator
        self._clock = clock

    def observe(
        self,
        context: LegacyRetirementContext,
    ) -> LegacyRetirementReport:
        return self._evaluate(context, state=context.observed_state)

    def assess(
        self,
        context: LegacyRetirementContext,
    ) -> LegacyRetirementReport:
        return self._evaluate(context)

    def unavailable(
        self,
        *,
        scope: LegacyRetirementScope,
        code: str,
        message: str,
    ) -> LegacyRetirementReport:
        generated_at = self._clock()
        check = LegacyRetirementCheck(
            code=code,
            passed=False,
            reason=message,
            remediation_hint=(
                "Mantenere il Legacy attivo finche Level 3 e tutti i gate "
                "obbligatori non risultano PASS."
            ),
        )
        gates = LegacyRetirementGateSummary(
            required_count=10,
            pass_count=2,
            warning_count=4,
            fail_count=4,
            status=RuntimeCertificationGateStatus.FAIL,
        )
        validation = LegacyRetirementValidationResult(
            allowed=False,
            checklist=(check,),
            gates=gates,
            evaluated_at=generated_at,
        )
        diagnostics = (
            LegacyRetirementDiagnosticsBuilder.from_validation(validation)
        )
        blocker = LegacyRetirementBlocker(
            code=code,
            severity=LegacyRetirementBlockerSeverity.CRITICAL,
            message=message,
        )
        return LegacyRetirementReport(
            scope=scope,
            state=LegacyRetirementState.BLOCKED,
            reason=message,
            checklist=validation.checklist,
            gates=gates,
            blockers=(blocker,),
            metrics=LegacyRetirementMetrics(
                legacy_active=True,
                legacy_standby=False,
                legacy_available=True,
                legacy_observable=True,
                legacy_recoverable=True,
                runtime_readiness=False,
                certification_level=RuntimeCertificationLevel.LEVEL_0,
                gate_status=RuntimeCertificationGateStatus.FAIL,
                rollback_available=True,
                runtime_stable_days=0,
                runtime_execution_count=0,
                runtime_success_percent=0,
                validation_latency_ms=0,
            ),
            diagnostics=diagnostics,
            duration_ms=0,
            generated_at=generated_at,
        )

    def _evaluate(
        self,
        context: LegacyRetirementContext,
        *,
        state: LegacyRetirementState | None = None,
    ) -> LegacyRetirementReport:
        started = perf_counter()
        validation_started = perf_counter()
        result = self._validator.validate(context)
        validation_ms = (perf_counter() - validation_started) * 1_000
        resolved_state = state or (
            LegacyRetirementState.READY_FOR_RETIREMENT
            if result.allowed
            else LegacyRetirementState.BLOCKED
        )
        diagnostics = (
            LegacyRetirementDiagnosticsBuilder.from_validation(result)
        )
        reason = self._reason(resolved_state)
        duration_ms = (perf_counter() - started) * 1_000
        return LegacyRetirementReport(
            scope=context.scope,
            state=resolved_state,
            reason=reason,
            checklist=result.checklist,
            gates=result.gates,
            blockers=context.open_blockers,
            metrics=LegacyRetirementMetrics(
                legacy_active=(
                    context.observed_state
                    is LegacyRetirementState.ACTIVE
                ),
                legacy_standby=(
                    context.observed_state
                    is LegacyRetirementState.STANDBY
                ),
                legacy_available=context.legacy_available,
                legacy_observable=context.legacy_observable,
                legacy_recoverable=context.legacy_recoverable,
                runtime_readiness=(
                    context.runtime_primary_stable
                    and context.all_operational_units_enabled
                ),
                certification_level=context.certification.level,
                gate_status=result.gates.status,
                rollback_available=context.rollback_available,
                runtime_stable_days=context.runtime_stable_days,
                runtime_execution_count=context.runtime_execution_count,
                runtime_success_percent=context.runtime_success_percent,
                validation_latency_ms=validation_ms,
            ),
            diagnostics=LegacyRetirementDiagnostics(
                items=diagnostics.items,
                generated_at=self._clock(),
            ),
            duration_ms=duration_ms,
            generated_at=self._clock(),
        )

    @staticmethod
    def _reason(state: LegacyRetirementState) -> str:
        reasons = {
            LegacyRetirementState.ACTIVE: (
                "Legacy attivo e integralmente disponibile."
            ),
            LegacyRetirementState.STANDBY: (
                "Legacy in standby, osservabile e recuperabile."
            ),
            LegacyRetirementState.READY_FOR_RETIREMENT: (
                "Precondizioni soddisfatte; nessuna rimozione eseguita."
            ),
            LegacyRetirementState.BLOCKED: (
                "Retirement bloccato in modalita fail-closed."
            ),
            LegacyRetirementState.RETIRED: (
                "Stato riservato a una futura decisione irreversibile."
            ),
        }
        return reasons[state]

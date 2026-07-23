from collections.abc import Callable
from datetime import datetime

from app.domain.execution_attempt import (
    ExecutionAttempt,
    ExecutionAttemptStatus,
)
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.runtime_authority import (
    AuthorityResolutionResult,
    AuthorityResolutionState,
)
from app.domain.runtime_shadow.comparator import PlanningComparator
from app.domain.runtime_shadow.models import (
    PlanningMismatchSeverity,
    RuntimeShadowDiagnostic,
    RuntimeShadowDiagnostics,
    RuntimeShadowDiagnosticSeverity,
    RuntimeShadowMetrics,
    RuntimeShadowResult,
    RuntimeShadowSnapshot,
    RuntimeShadowSource,
    RuntimeShadowState,
)


class RuntimeShadowService:
    def __init__(
        self,
        *,
        comparator: PlanningComparator,
        clock: Callable[[], datetime],
    ) -> None:
        self._comparator = comparator
        self._clock = clock

    def compare(
        self,
        *,
        legacy: RuntimeShadowSnapshot,
        runtime: RuntimeShadowSnapshot,
        authority: AuthorityResolutionResult,
        intent: ExecutionIntent,
        attempt: ExecutionAttempt | None,
    ) -> RuntimeShadowResult:
        generated_at = self._clock()
        failures = self._validate_pipeline(
            legacy=legacy,
            runtime=runtime,
            authority=authority,
            intent=intent,
            attempt=attempt,
        )
        if failures:
            return RuntimeShadowResult(
                state=RuntimeShadowState.REJECTED,
                diagnostics=RuntimeShadowDiagnostics(
                    items=tuple(
                        RuntimeShadowDiagnostic(
                            code=code,
                            severity=RuntimeShadowDiagnosticSeverity.ERROR,
                            message=message,
                        )
                        for code, message in failures
                    ),
                    generated_at=generated_at,
                ),
                generated_at=generated_at,
            )

        comparison = self._comparator.compare(
            legacy=legacy,
            runtime=runtime,
        )
        critical = sum(
            mismatch.severity is PlanningMismatchSeverity.CRITICAL
            for mismatch in comparison.mismatches
        )
        high = sum(
            mismatch.severity is PlanningMismatchSeverity.HIGH
            for mismatch in comparison.mismatches
        )
        metrics = RuntimeShadowMetrics(
            parity_percent=comparison.report.parity_percent,
            critical_mismatch=critical,
            high_mismatch=high,
            execution_simulated=True,
            comparison_time_ms=comparison.report.comparison_time_ms,
            shadow_latency_ms=abs(
                (runtime.generated_at - legacy.generated_at).total_seconds()
                * 1_000
            ),
            duplicate_execution=0,
        )
        severity = (
            RuntimeShadowDiagnosticSeverity.ERROR
            if critical
            else (
                RuntimeShadowDiagnosticSeverity.WARNING
                if comparison.mismatches
                else RuntimeShadowDiagnosticSeverity.INFO
            )
        )
        diagnostic = RuntimeShadowDiagnostic(
            code=(
                "SHADOW_PERFECT_MATCH"
                if comparison.report.perfect_match
                else "SHADOW_MISMATCH_DETECTED"
            ),
            severity=severity,
            message=(
                "Shadow Runtime e Legacy coincidono. Nessun effetto operativo."
                if comparison.report.perfect_match
                else (
                    "Shadow Runtime completato con divergenze; "
                    "nessun effetto operativo applicato."
                )
            ),
        )
        return RuntimeShadowResult(
            state=RuntimeShadowState.COMPLETED,
            report=comparison.report,
            mismatches=comparison.mismatches,
            metrics=metrics,
            diagnostics=RuntimeShadowDiagnostics(
                items=(diagnostic,),
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    @staticmethod
    def _validate_pipeline(
        *,
        legacy: RuntimeShadowSnapshot,
        runtime: RuntimeShadowSnapshot,
        authority: AuthorityResolutionResult,
        intent: ExecutionIntent,
        attempt: ExecutionAttempt | None,
    ) -> tuple[tuple[str, str], ...]:
        failures: list[tuple[str, str]] = []
        authority_valid = (
            authority.state is AuthorityResolutionState.WRITE_ALLOWED
            and authority.decision is not None
        )
        if not authority_valid:
            failures.append(("AUTHORITY_INVALID", "Authority non valida."))
        if intent.status is not ExecutionIntentStatus.READY:
            failures.append(
                ("EXECUTION_INTENT_NOT_READY", "Execution Intent non READY.")
            )
        if attempt is None:
            failures.append(
                ("EXECUTION_ATTEMPT_MISSING", "Execution Attempt assente.")
            )
        elif attempt.status not in {
            ExecutionAttemptStatus.PENDING,
            ExecutionAttemptStatus.LOCK_ACQUIRED,
            ExecutionAttemptStatus.READY_TO_EXECUTE,
        }:
            failures.append(
                ("EXECUTION_ATTEMPT_INVALID", "Execution Attempt non valido.")
            )
        if (
            attempt is not None
            and attempt.scope.execution_intent_id != intent.intent_id
        ):
            failures.append(
                ("ATTEMPT_INTENT_MISMATCH", "Attempt e Intent non coerenti.")
            )
        if legacy.source is not RuntimeShadowSource.LEGACY:
            failures.append(
                ("LEGACY_SOURCE_INVALID", "Snapshot Legacy non valido.")
            )
        if runtime.source is not RuntimeShadowSource.RUNTIME:
            failures.append(
                ("RUNTIME_SOURCE_INVALID", "Snapshot Runtime non valido.")
            )
        if legacy.publication.status is not ExecutionPublicationStatus.PUBLISHED:
            failures.append(
                ("PUBLICATION_INVALID", "Publication Legacy non valida.")
            )
        if runtime.publication.status is not ExecutionPublicationStatus.PUBLISHED:
            failures.append(
                ("PUBLICATION_INVALID", "Publication Runtime non valida.")
            )
        legacy_matches_intent = (
            legacy.scope.identity == intent.scope.operational_identity
            and legacy.publication.publication_id
            == intent.scope.publication_id
            and legacy.publication.publication_version
            == intent.scope.publication_version
        )
        if not legacy_matches_intent:
            failures.append(
                ("SHADOW_SCOPE_INVALID", "Legacy e Intent non coerenti.")
            )
        if attempt is not None and (
            attempt.publication_id != legacy.publication.publication_id
            or attempt.publication_version
            != legacy.publication.publication_version
        ):
            failures.append(
                ("ATTEMPT_PUBLICATION_MISMATCH", "Attempt e Publication non coerenti.")
            )
        if authority.decision is not None and attempt is not None and (
            authority.decision.decision_id != intent.authority_decision_id
            or authority.decision.decision_id
            != attempt.authority_decision_id
            or authority.decision.fencing_token != intent.fencing_token
            or authority.decision.fencing_token != attempt.fencing_token
        ):
            failures.append(
                ("FENCING_TOKEN_INVALID", "Fencing obsoleto o non coerente.")
            )
        return tuple(failures)

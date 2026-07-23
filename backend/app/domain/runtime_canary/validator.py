from app.domain.execution_attempt import ExecutionAttemptStatus
from app.domain.execution_intent import (
    ExecutionIntentStatus,
    ExecutionPublicationStatus,
)
from app.domain.planning_runtime import PlanningRuntimeOutputStatus
from app.domain.runtime_authority import AuthorityResolutionState
from app.domain.runtime_canary.models import (
    RuntimeCanaryDiagnostic,
    RuntimeCanaryDiagnostics,
    RuntimeCanaryDiagnosticSeverity,
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryStatus,
)
from app.domain.runtime_shadow import RuntimeShadowState


class RuntimeCanaryValidator:
    @staticmethod
    def _error(code: str, message: str) -> RuntimeCanaryDiagnostic:
        return RuntimeCanaryDiagnostic(
            code=code,
            severity=RuntimeCanaryDiagnosticSeverity.ERROR,
            message=message,
        )

    def validate(
        self,
        context: RuntimeCanaryEvaluationContext,
    ) -> RuntimeCanaryDiagnostics:
        issues: list[RuntimeCanaryDiagnostic] = []
        session = context.session
        authority = context.authority
        intent = context.intent
        attempt = context.attempt
        publication = context.publication

        if session.status is not RuntimeCanaryStatus.CREATED:
            issues.append(
                self._error(
                    "CANARY_SESSION_INVALID",
                    "La sessione Canary non e nello stato CREATED.",
                )
            )
        if (
            authority.state is not AuthorityResolutionState.WRITE_ALLOWED
            or authority.decision is None
        ):
            issues.append(
                self._error("AUTHORITY_INVALID", "Authority non valida.")
            )
        if intent.status is not ExecutionIntentStatus.READY:
            issues.append(
                self._error(
                    "EXECUTION_INTENT_NOT_READY",
                    "Execution Intent non READY.",
                )
            )
        if attempt is None:
            issues.append(
                self._error(
                    "EXECUTION_ATTEMPT_MISSING",
                    "Execution Attempt assente.",
                )
            )
        elif attempt.status is not ExecutionAttemptStatus.READY_TO_EXECUTE:
            issues.append(
                self._error(
                    "EXECUTION_ATTEMPT_NOT_READY",
                    "Execution Attempt non READY_TO_EXECUTE.",
                )
            )
        if publication.status is not ExecutionPublicationStatus.PUBLISHED:
            issues.append(
                self._error("PUBLICATION_INVALID", "Publication non valida.")
            )
        expected_scope = (
            session.organization_id,
            session.operational_unit_id,
            session.planning_date,
            session.timezone,
        )
        if intent.scope.operational_identity != expected_scope:
            issues.append(
                self._error(
                    "CANARY_INTENT_SCOPE_MISMATCH",
                    "Sessione Canary e Execution Intent non coerenti.",
                )
            )
        if (
            publication.organization_id != session.organization_id
            or publication.operational_unit_id != session.operational_unit_id
            or publication.planning_date != session.planning_date
            or publication.publication_id != session.publication_id
            or publication.publication_version
            != session.publication_version
        ):
            issues.append(
                self._error(
                    "CANARY_PUBLICATION_SCOPE_MISMATCH",
                    "Sessione Canary e Publication non coerenti.",
                )
            )
        if (
            intent.scope.publication_id != publication.publication_id
            or intent.scope.publication_version
            != publication.publication_version
        ):
            issues.append(
                self._error(
                    "PUBLICATION_INTENT_MISMATCH",
                    "Publication ed Execution Intent non coerenti.",
                )
            )
        if authority.decision is not None and (
            str(authority.decision.decision_id) != session.authority_decision
            or authority.decision.decision_id
            != intent.authority_decision_id
        ):
            issues.append(
                self._error(
                    "AUTHORITY_DECISION_MISMATCH",
                    "Authority Decision non coerente con la sessione.",
                )
            )
        if attempt is not None and (
            attempt.scope.execution_intent_id != intent.intent_id
            or attempt.publication_id != publication.publication_id
            or attempt.publication_version != publication.publication_version
            or attempt.authority_decision_id != intent.authority_decision_id
            or attempt.fencing_token != intent.fencing_token
        ):
            issues.append(
                self._error(
                    "CANARY_ATTEMPT_MISMATCH",
                    "Execution Attempt non coerente con la pipeline Canary.",
                )
            )
        if not context.producer_available:
            issues.append(
                self._error(
                    "PRODUCER_NOT_AVAILABLE",
                    "Runtime Producer non disponibile.",
                )
            )
        if not context.comparator_available:
            issues.append(
                self._error(
                    "COMPARATOR_NOT_AVAILABLE",
                    "Shadow Comparator non disponibile.",
                )
            )
        if not context.parity_engine_available:
            issues.append(
                self._error(
                    "PARITY_ENGINE_NOT_AVAILABLE",
                    "Parity Engine non disponibile.",
                )
            )
        if context.producer_result is None:
            issues.append(
                self._error(
                    "PRODUCER_RESULT_MISSING",
                    "Runtime Producer non ha restituito un risultato.",
                )
            )
        elif (
            context.producer_result.status
            is not PlanningRuntimeOutputStatus.READY
            or context.producer_result.snapshot is None
        ):
            issues.append(
                self._error(
                    "PRODUCER_RESULT_INVALID",
                    "Runtime Producer non ha prodotto uno snapshot valido.",
                )
            )
        if context.shadow_result is None:
            issues.append(
                self._error(
                    "COMPARATOR_RESULT_MISSING",
                    "Shadow Comparator non ha restituito un risultato.",
                )
            )
        elif (
            context.shadow_result.state is not RuntimeShadowState.COMPLETED
            or context.shadow_result.report is None
            or context.shadow_result.metrics is None
        ):
            issues.append(
                self._error(
                    "COMPARATOR_RESULT_INVALID",
                    "Shadow Comparator non ha completato il confronto.",
                )
            )

        if not issues:
            issues.append(
                RuntimeCanaryDiagnostic(
                    code="CANARY_PREREQUISITES_VALID",
                    severity=RuntimeCanaryDiagnosticSeverity.INFO,
                    message="Prerequisiti Canary validi.",
                )
            )
        return RuntimeCanaryDiagnostics(
            items=tuple(issues),
            generated_at=session.started_at,
        )

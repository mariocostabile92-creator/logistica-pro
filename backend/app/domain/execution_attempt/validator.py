from datetime import datetime

from app.domain.execution_attempt.models import (
    ExecutionAttempt,
    ExecutionAttemptCommand,
    ExecutionAttemptMode,
    ExecutionAttemptStatus,
    ExecutionAttemptValidationResult,
    ExecutionAttemptValidationRule,
)
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionIntentMode,
    ExecutionIntentStatus,
    ExecutionPublicationReference,
    ExecutionPublicationStatus,
)
from app.domain.runtime_authority import (
    AuthorityResolutionResult,
    AuthorityResolutionState,
)


def _rule(
    code: str,
    passed: bool,
    reason: str,
    remediation_hint: str,
) -> ExecutionAttemptValidationRule:
    return ExecutionAttemptValidationRule(
        code=code,
        passed=passed,
        reason=reason,
        remediation_hint=remediation_hint,
    )


class ExecutionAttemptValidator:
    def validate(
        self,
        *,
        command: ExecutionAttemptCommand,
        intent: ExecutionIntent | None,
        publication: ExecutionPublicationReference | None,
        authority: AuthorityResolutionResult,
        active_attempt: ExecutionAttempt | None,
        evaluated_at: datetime,
    ) -> ExecutionAttemptValidationResult:
        intent_present = intent is not None
        intent_ready = bool(
            intent and intent.status is ExecutionIntentStatus.READY
        )
        intent_not_cancelled = bool(
            intent and intent.status is not ExecutionIntentStatus.CANCELLED
        )
        intent_scope_matches = bool(
            intent
            and intent.scope.organization_id
            == command.series_scope.organization_id
            and intent.scope.operational_unit_id
            == command.series_scope.operational_unit_id
            and intent.scope.planning_date == command.series_scope.planning_date
            and intent.scope.timezone == command.series_scope.timezone
            and intent.intent_id == command.series_scope.execution_intent_id
        )
        version_matches = bool(
            intent
            and int(intent.version) == command.expected_intent_version
        )
        mode_supported = bool(intent and self.mode_for(intent) is not None)
        authority_allowed = (
            authority.state is AuthorityResolutionState.WRITE_ALLOWED
            and authority.decision is not None
        )
        authority_matches = bool(
            authority.decision
            and authority.decision.decision_id == command.authority_decision_id
            and authority.scope.identity
            == (
                command.series_scope.organization_id,
                command.series_scope.operational_unit_id,
                command.series_scope.planning_date,
                command.series_scope.timezone,
            )
        )
        fencing_matches = bool(
            authority.decision
            and authority.decision.fencing_token == command.fencing_token
        )
        publication_present = publication is not None
        publication_active = bool(
            publication
            and publication.status is ExecutionPublicationStatus.PUBLISHED
        )
        publication_matches = bool(
            intent
            and publication
            and publication.organization_id == intent.scope.organization_id
            and publication.operational_unit_id
            == intent.scope.operational_unit_id
            and publication.planning_date == intent.scope.planning_date
            and publication.publication_id == intent.scope.publication_id
            and publication.publication_version
            == intent.scope.publication_version
            and publication.fingerprint == intent.publication_fingerprint
        )
        lock_available = active_attempt is None
        rules = (
            _rule(
                "EXECUTION_INTENT_PRESENT",
                intent_present,
                (
                    "Execution Intent disponibile."
                    if intent_present
                    else "Execution Intent non disponibile."
                ),
                "Crea o ricarica un Execution Intent valido.",
            ),
            _rule(
                "EXECUTION_INTENT_READY",
                intent_ready,
                (
                    "Execution Intent READY."
                    if intent_ready
                    else "Execution Intent non READY."
                ),
                "Porta l'Intent nello stato READY prima del tentativo.",
            ),
            _rule(
                "EXECUTION_INTENT_NOT_CANCELLED",
                intent_not_cancelled,
                (
                    "Execution Intent non cancellato."
                    if intent_not_cancelled
                    else "Execution Intent cancellato."
                ),
                "Usa un Intent corrente e non cancellato.",
            ),
            _rule(
                "EXECUTION_INTENT_SCOPE_COHERENT",
                intent_scope_matches,
                (
                    "Scope Intent coerente."
                    if intent_scope_matches
                    else "Scope Intent non coerente."
                ),
                "Ricarica l'Intent per lo scope operativo richiesto.",
            ),
            _rule(
                "EXECUTION_INTENT_VERSION_COHERENT",
                version_matches,
                (
                    "Versione Intent coerente."
                    if version_matches
                    else "Version mismatch."
                ),
                "Usa la versione corrente dell'Intent.",
            ),
            _rule(
                "EXECUTION_ATTEMPT_MODE_SUPPORTED",
                mode_supported,
                (
                    "Mode Attempt supportato."
                    if mode_supported
                    else "Mode Intent non supportato per Execution Attempt."
                ),
                "Usa NORMAL, SHADOW o VERIFY.",
            ),
            _rule(
                "AUTHORITY_WRITE_ALLOWED",
                authority_allowed,
                (
                    "Authority valida."
                    if authority_allowed
                    else "Authority non valida."
                ),
                "Risolvi Authority prima di creare il tentativo.",
            ),
            _rule(
                "AUTHORITY_DECISION_COHERENT",
                authority_matches,
                (
                    "Authority Decision coerente."
                    if authority_matches
                    else "Authority Decision o scope non coerente."
                ),
                "Ricarica la decisione Authority corrente.",
            ),
            _rule(
                "FENCING_TOKEN_COHERENT",
                fencing_matches,
                (
                    "Fencing token valido."
                    if fencing_matches
                    else "Fencing obsoleto."
                ),
                "Usa il fencing token corrente.",
            ),
            _rule(
                "PUBLICATION_PRESENT",
                publication_present,
                (
                    "Publication disponibile."
                    if publication_present
                    else "Publication non disponibile."
                ),
                "Ricarica la Publication dell'Intent.",
            ),
            _rule(
                "PUBLICATION_ACTIVE",
                publication_active,
                (
                    "Publication valida."
                    if publication_active
                    else "Publication non valida."
                ),
                "Usa una Publication pubblicata e corrente.",
            ),
            _rule(
                "PUBLICATION_COHERENT",
                publication_matches,
                (
                    "Publication coerente con l'Intent."
                    if publication_matches
                    else "Publication non coerente con l'Intent."
                ),
                "Ricarica Publication e Intent immutabili.",
            ),
            _rule(
                "LOGICAL_LOCK_AVAILABLE",
                lock_available,
                (
                    "Lock logico disponibile."
                    if lock_available
                    else "Lock non disponibile."
                ),
                "Attendi la chiusura del tentativo attivo.",
            ),
        )
        allowed = all(rule.passed for rule in rules)
        return ExecutionAttemptValidationResult(
            status=(
                ExecutionAttemptStatus.PENDING
                if allowed
                else ExecutionAttemptStatus.REJECTED
            ),
            allowed=allowed,
            rules=rules,
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def rejection(
        *,
        code: str,
        reason: str,
        remediation_hint: str,
        evaluated_at: datetime,
    ) -> ExecutionAttemptValidationResult:
        return ExecutionAttemptValidationResult(
            status=ExecutionAttemptStatus.REJECTED,
            allowed=False,
            rules=(
                _rule(code, False, reason, remediation_hint),
            ),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def mode_for(
        intent: ExecutionIntent,
    ) -> ExecutionAttemptMode | None:
        mapping = {
            ExecutionIntentMode.NORMAL: ExecutionAttemptMode.NORMAL,
            ExecutionIntentMode.SHADOW: ExecutionAttemptMode.SHADOW,
            ExecutionIntentMode.VERIFY: ExecutionAttemptMode.VERIFY,
        }
        return mapping.get(intent.scope.execution_mode)

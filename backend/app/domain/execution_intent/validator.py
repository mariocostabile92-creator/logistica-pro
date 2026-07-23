from datetime import datetime

from app.domain.execution_intent.models import (
    ExecutionIntent,
    ExecutionIntentCommand,
    ExecutionIntentStatus,
    ExecutionIntentValidationResult,
    ExecutionIntentValidationRule,
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
) -> ExecutionIntentValidationRule:
    return ExecutionIntentValidationRule(
        code=code,
        passed=passed,
        reason=reason,
        remediation_hint=remediation_hint,
    )


class ExecutionIntentValidator:
    def validate(
        self,
        *,
        command: ExecutionIntentCommand,
        publication: ExecutionPublicationReference | None,
        authority: AuthorityResolutionResult,
        existing_intent: ExecutionIntent | None,
        evaluated_at: datetime,
    ) -> ExecutionIntentValidationResult:
        authority_allowed = (
            authority.state is AuthorityResolutionState.WRITE_ALLOWED
            and authority.decision is not None
        )
        authority_matches = bool(
            authority.decision
            and authority.decision.decision_id == command.authority_decision_id
            and authority.scope.identity == command.scope.operational_identity
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
        publication_scope_matches = bool(
            publication
            and publication.organization_id == command.scope.organization_id
            and (
                publication.operational_unit_id
                == command.scope.operational_unit_id
            )
            and publication.planning_date == command.scope.planning_date
            and publication.publication_id == command.scope.publication_id
        )
        version_matches = bool(
            publication
            and publication.publication_version
            == command.scope.publication_version
        )
        fingerprint_matches = bool(
            publication
            and publication.fingerprint == command.publication_fingerprint
        )
        rules = (
            _rule(
                "AUTHORITY_WRITE_ALLOWED",
                authority_allowed,
                (
                    "Authority valida."
                    if authority_allowed
                    else "Authority non valida."
                ),
                "Risolvi Authority prima di creare l'Intent.",
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
                    else "Fencing token obsoleto."
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
                "Pubblica un piano valido prima di creare l'Intent.",
            ),
            _rule(
                "PUBLICATION_ACTIVE",
                publication_active,
                self._publication_status_reason(publication),
                "Usa una Publication corrente, non revocata o superata.",
            ),
            _rule(
                "PUBLICATION_SCOPE_COHERENT",
                publication_scope_matches,
                (
                    "Scope Publication coerente."
                    if publication_scope_matches
                    else "Scope Publication non coerente."
                ),
                "Ricarica la Publication per lo scope richiesto.",
            ),
            _rule(
                "PUBLICATION_VERSION_COHERENT",
                version_matches,
                (
                    "Versione Publication coerente."
                    if version_matches
                    else "Version mismatch."
                ),
                "Usa la versione corrente della Publication.",
            ),
            _rule(
                "PUBLICATION_FINGERPRINT_COHERENT",
                fingerprint_matches,
                (
                    "Fingerprint Publication coerente."
                    if fingerprint_matches
                    else "Fingerprint Publication non coerente."
                ),
                "Ricarica il contratto immutabile della Publication.",
            ),
            _rule(
                "EXPECTED_VERSION_COHERENT",
                command.expected_version == 0,
                (
                    "Expected version valida per un nuovo Intent."
                    if command.expected_version == 0
                    else "Version mismatch."
                ),
                "Per un nuovo Intent usa expected_version 0.",
            ),
            _rule(
                "EXECUTION_INTENT_UNIQUE",
                existing_intent is None,
                (
                    "Nessun Intent attivo duplicato."
                    if existing_intent is None
                    else "Execution Intent gia esistente."
                ),
                "Consulta l'Intent esistente per Publication e mode.",
            ),
        )
        allowed = all(rule.passed for rule in rules)
        return ExecutionIntentValidationResult(
            status=(
                ExecutionIntentStatus.READY
                if allowed
                else ExecutionIntentStatus.REJECTED
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
    ) -> ExecutionIntentValidationResult:
        return ExecutionIntentValidationResult(
            status=ExecutionIntentStatus.REJECTED,
            allowed=False,
            rules=(
                _rule(code, False, reason, remediation_hint),
            ),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def accepted_replay(
        *,
        evaluated_at: datetime,
    ) -> ExecutionIntentValidationResult:
        return ExecutionIntentValidationResult(
            status=ExecutionIntentStatus.READY,
            allowed=True,
            rules=(
                _rule(
                    "IDEMPOTENT_REPLAY",
                    True,
                    "Comando gia acquisito: restituito lo stesso Intent.",
                    "Nessuna azione richiesta.",
                ),
            ),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _publication_status_reason(
        publication: ExecutionPublicationReference | None,
    ) -> str:
        if publication is None:
            return "Publication non disponibile."
        if publication.status is ExecutionPublicationStatus.SUPERSEDED:
            return "Publication superseded."
        if publication.status is ExecutionPublicationStatus.REVOKED:
            return "Publication revoked."
        return "Publication valida."

from collections.abc import Callable
from datetime import datetime

from app.domain.execution_intent.diagnostics import (
    build_execution_intent_diagnostics,
)
from app.domain.execution_intent.key import (
    execution_intent_key,
    execution_intent_payload_fingerprint,
)
from app.domain.execution_intent.models import (
    ExecutionIntent,
    ExecutionIntentCommand,
    ExecutionIntentCreationResult,
    ExecutionIntentId,
    ExecutionIntentScope,
    ExecutionIntentStatus,
    ExecutionIntentVersion,
    ExecutionPublicationReference,
)
from app.domain.execution_intent.repository import (
    ExecutionIntentRepository,
    ExecutionIntentRepositoryConflictError,
)
from app.domain.execution_intent.validator import ExecutionIntentValidator
from app.domain.runtime_authority import AuthorityResolutionResult


class ExecutionIntentService:
    def __init__(
        self,
        *,
        repository: ExecutionIntentRepository,
        validator: ExecutionIntentValidator,
        clock: Callable[[], datetime],
        identifier_factory: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._clock = clock
        self._identifier_factory = identifier_factory

    def current(self, scope: ExecutionIntentScope) -> ExecutionIntent | None:
        return self._repository.get_by_key(execution_intent_key(scope))

    def create(
        self,
        *,
        command: ExecutionIntentCommand,
        publication: ExecutionPublicationReference | None,
        authority: AuthorityResolutionResult,
    ) -> ExecutionIntentCreationResult:
        evaluated_at = self._clock()
        intent_key = execution_intent_key(command.scope)
        payload_fingerprint = execution_intent_payload_fingerprint(
            command,
            intent_key=intent_key,
        )
        idempotent = self._repository.get_by_idempotency_key(
            organization_id=command.scope.organization_id,
            idempotency_key=command.idempotency_key,
        )
        if idempotent is not None:
            if (
                idempotent.intent_key == intent_key
                and idempotent.payload_fingerprint == payload_fingerprint
            ):
                return self._accepted_replay(idempotent, evaluated_at)
            return self._rejected(
                code="IDEMPOTENCY_KEY_CONFLICT",
                reason="Idempotency key gia usata con un payload differente.",
                remediation_hint="Usa la key originale o genera una nuova key.",
                evaluated_at=evaluated_at,
            )

        existing = self._repository.get_by_key(intent_key)
        validation = self._validator.validate(
            command=command,
            publication=publication,
            authority=authority,
            existing_intent=existing,
            evaluated_at=evaluated_at,
        )
        if not validation.allowed:
            return ExecutionIntentCreationResult(
                status=ExecutionIntentStatus.REJECTED,
                validation=validation,
                diagnostics=build_execution_intent_diagnostics(validation),
                generated_at=evaluated_at,
            )

        intent = ExecutionIntent(
            intent_id=ExecutionIntentId(
                f"execution-intent-{self._identifier_factory()}"
            ),
            intent_key=intent_key,
            scope=command.scope,
            version=ExecutionIntentVersion(1),
            status=ExecutionIntentStatus.READY,
            publication_fingerprint=command.publication_fingerprint,
            authority_decision_id=command.authority_decision_id,
            fencing_token=command.fencing_token,
            idempotency_key=command.idempotency_key,
            payload_fingerprint=payload_fingerprint,
            actor=command.actor,
            created_at=evaluated_at,
        )
        try:
            self._repository.append(intent)
        except ExecutionIntentRepositoryConflictError:
            raced = self._repository.get_by_idempotency_key(
                organization_id=command.scope.organization_id,
                idempotency_key=command.idempotency_key,
            )
            if (
                raced is not None
                and raced.intent_key == intent_key
                and raced.payload_fingerprint == payload_fingerprint
            ):
                return self._accepted_replay(raced, evaluated_at)
            return self._rejected(
                code="EXECUTION_INTENT_CONFLICT",
                reason="Execution Intent concorrente gia registrato.",
                remediation_hint="Ricarica l'Intent corrente.",
                evaluated_at=evaluated_at,
            )
        return ExecutionIntentCreationResult(
            status=ExecutionIntentStatus.READY,
            intent=intent,
            validation=validation,
            diagnostics=build_execution_intent_diagnostics(validation),
            generated_at=evaluated_at,
        )

    def _accepted_replay(
        self,
        intent: ExecutionIntent,
        evaluated_at: datetime,
    ) -> ExecutionIntentCreationResult:
        validation = self._validator.accepted_replay(
            evaluated_at=evaluated_at
        )
        return ExecutionIntentCreationResult(
            status=ExecutionIntentStatus.READY,
            intent=intent,
            validation=validation,
            diagnostics=build_execution_intent_diagnostics(validation),
            idempotent=True,
            generated_at=evaluated_at,
        )

    def _rejected(
        self,
        *,
        code: str,
        reason: str,
        remediation_hint: str,
        evaluated_at: datetime,
    ) -> ExecutionIntentCreationResult:
        validation = self._validator.rejection(
            code=code,
            reason=reason,
            remediation_hint=remediation_hint,
            evaluated_at=evaluated_at,
        )
        return ExecutionIntentCreationResult(
            status=ExecutionIntentStatus.REJECTED,
            validation=validation,
            diagnostics=build_execution_intent_diagnostics(validation),
            generated_at=evaluated_at,
        )

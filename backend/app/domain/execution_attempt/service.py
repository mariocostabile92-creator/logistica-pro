from collections.abc import Callable
from datetime import datetime

from app.domain.execution_attempt.diagnostics import (
    build_execution_attempt_diagnostics,
)
from app.domain.execution_attempt.models import (
    ExecutionAttempt,
    ExecutionAttemptCommand,
    ExecutionAttemptCreationResult,
    ExecutionAttemptDiagnosticSeverity,
    ExecutionAttemptHistory,
    ExecutionAttemptId,
    ExecutionAttemptScope,
    ExecutionAttemptSeriesScope,
    ExecutionAttemptStatus,
    ExecutionAttemptValidationResult,
    ExecutionAttemptVersion,
    LockDiagnostic,
    LockDiagnostics,
    LockState,
)
from app.domain.execution_attempt.repository import (
    ExecutionAttemptRepository,
    ExecutionAttemptRepositoryConflictError,
)
from app.domain.execution_attempt.validator import ExecutionAttemptValidator
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionPublicationReference,
)
from app.domain.runtime_authority import AuthorityResolutionResult


class ExecutionAttemptService:
    def __init__(
        self,
        *,
        repository: ExecutionAttemptRepository,
        validator: ExecutionAttemptValidator,
        clock: Callable[[], datetime],
        identifier_factory: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._clock = clock
        self._identifier_factory = identifier_factory

    def current(
        self,
        scope: ExecutionAttemptScope,
    ) -> ExecutionAttempt | None:
        return self._repository.get_current(scope)

    def history(
        self,
        scope: ExecutionAttemptSeriesScope,
    ) -> ExecutionAttemptHistory:
        return self._repository.history(scope)

    def create(
        self,
        *,
        command: ExecutionAttemptCommand,
        intent: ExecutionIntent | None,
        publication: ExecutionPublicationReference | None,
        authority: AuthorityResolutionResult,
    ) -> ExecutionAttemptCreationResult:
        evaluated_at = self._clock()
        attempt_number = self._repository.next_attempt_number(
            command.series_scope
        )
        validation = self._validator.validate(
            command=command,
            intent=intent,
            publication=publication,
            authority=authority,
            active_attempt=self._repository.get_active(command.series_scope),
            evaluated_at=evaluated_at,
        )
        if not validation.allowed or intent is None or publication is None:
            return self._rejected(validation, evaluated_at)

        mode = self._validator.mode_for(intent)
        if mode is None:
            return self._rejected(validation, evaluated_at)
        lock_diagnostics = LockDiagnostics(
            state=LockState.AVAILABLE,
            items=(
                LockDiagnostic(
                    code="LOGICAL_LOCK_AVAILABLE",
                    severity=ExecutionAttemptDiagnosticSeverity.INFO,
                    message=(
                        "Lock logico disponibile; nessun lock distribuito acquisito."
                    ),
                ),
            ),
            generated_at=evaluated_at,
        )
        attempt = ExecutionAttempt(
            attempt_id=ExecutionAttemptId(
                f"execution-attempt-{self._identifier_factory()}"
            ),
            scope=ExecutionAttemptScope(
                **command.series_scope.model_dump(),
                attempt_number=attempt_number,
            ),
            mode=mode,
            version=ExecutionAttemptVersion(1),
            status=ExecutionAttemptStatus.PENDING,
            intent_version=int(intent.version),
            publication_id=publication.publication_id,
            publication_version=publication.publication_version,
            publication_fingerprint=publication.fingerprint,
            authority_decision_id=command.authority_decision_id,
            fencing_token=command.fencing_token,
            actor=command.actor,
            created_at=evaluated_at,
            lock_state=LockState.AVAILABLE,
            lock_diagnostics=lock_diagnostics,
        )
        try:
            self._repository.append(attempt)
        except ExecutionAttemptRepositoryConflictError:
            rejected = self._validator.rejection(
                code="EXECUTION_ATTEMPT_CONFLICT",
                reason="Lock non disponibile o attempt_number gia acquisito.",
                remediation_hint="Ricarica la cronologia dei tentativi.",
                evaluated_at=evaluated_at,
            )
            return self._rejected(rejected, evaluated_at)
        return ExecutionAttemptCreationResult(
            status=ExecutionAttemptStatus.PENDING,
            attempt=attempt,
            validation=validation,
            diagnostics=build_execution_attempt_diagnostics(validation),
            generated_at=evaluated_at,
        )

    @staticmethod
    def _rejected(
        validation: ExecutionAttemptValidationResult,
        evaluated_at: datetime,
    ) -> ExecutionAttemptCreationResult:
        return ExecutionAttemptCreationResult(
            status=ExecutionAttemptStatus.REJECTED,
            validation=validation,
            diagnostics=build_execution_attempt_diagnostics(validation),
            generated_at=evaluated_at,
        )

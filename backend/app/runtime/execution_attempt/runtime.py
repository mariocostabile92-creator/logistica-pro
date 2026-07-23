from collections.abc import Callable
from datetime import datetime

from app.domain.execution_attempt import (
    ExecutionAttemptCommand,
    ExecutionAttemptCreationResult,
    ExecutionAttemptDiagnostic,
    ExecutionAttemptDiagnostics,
    ExecutionAttemptDiagnosticSeverity,
    ExecutionAttemptRuntimeReport,
    ExecutionAttemptScope,
    ExecutionAttemptService,
)
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionPublicationReference,
)
from app.domain.runtime_authority import AuthorityResolutionResult


class ExecutionAttemptRuntime:
    def __init__(
        self,
        *,
        service: ExecutionAttemptService,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._clock = clock

    def current(
        self,
        scope: ExecutionAttemptScope,
    ) -> ExecutionAttemptRuntimeReport:
        generated_at = self._clock()
        attempt = self._service.current(scope)
        diagnostic = ExecutionAttemptDiagnostic(
            code=(
                "EXECUTION_ATTEMPT_FOUND"
                if attempt is not None
                else "EXECUTION_ATTEMPT_NOT_FOUND"
            ),
            severity=ExecutionAttemptDiagnosticSeverity.INFO,
            message=(
                "Execution Attempt disponibile."
                if attempt is not None
                else "Nessun Execution Attempt disponibile per lo scope."
            ),
        )
        return ExecutionAttemptRuntimeReport(
            attempt=attempt,
            diagnostics=ExecutionAttemptDiagnostics(
                items=(diagnostic,),
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    def create(
        self,
        *,
        command: ExecutionAttemptCommand,
        intent: ExecutionIntent | None,
        publication: ExecutionPublicationReference | None,
        authority: AuthorityResolutionResult,
    ) -> ExecutionAttemptCreationResult:
        return self._service.create(
            command=command,
            intent=intent,
            publication=publication,
            authority=authority,
        )

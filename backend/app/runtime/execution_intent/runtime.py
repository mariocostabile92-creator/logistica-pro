from collections.abc import Callable
from datetime import datetime

from app.domain.execution_intent import (
    ExecutionIntentCommand,
    ExecutionIntentCreationResult,
    ExecutionIntentDiagnostic,
    ExecutionIntentDiagnostics,
    ExecutionIntentDiagnosticSeverity,
    ExecutionIntentRuntimeReport,
    ExecutionIntentScope,
    ExecutionIntentService,
)
from app.domain.runtime_authority import AuthorityScope
from app.runtime.execution_intent.contracts import (
    ExecutionIntentAuthorityProvider,
    ExecutionPublicationProvider,
)


class ExecutionIntentRuntime:
    def __init__(
        self,
        *,
        service: ExecutionIntentService,
        publication_provider: ExecutionPublicationProvider,
        authority_provider: ExecutionIntentAuthorityProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._publication_provider = publication_provider
        self._authority_provider = authority_provider
        self._clock = clock

    def current(
        self,
        scope: ExecutionIntentScope,
    ) -> ExecutionIntentRuntimeReport:
        generated_at = self._clock()
        intent = self._service.current(scope)
        diagnostic = ExecutionIntentDiagnostic(
            code=(
                "EXECUTION_INTENT_FOUND"
                if intent is not None
                else "EXECUTION_INTENT_NOT_FOUND"
            ),
            severity=ExecutionIntentDiagnosticSeverity.INFO,
            message=(
                "Execution Intent disponibile."
                if intent is not None
                else "Nessun Execution Intent disponibile per lo scope."
            ),
        )
        return ExecutionIntentRuntimeReport(
            intent=intent,
            diagnostics=ExecutionIntentDiagnostics(
                items=(diagnostic,),
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    def create(
        self,
        command: ExecutionIntentCommand,
    ) -> ExecutionIntentCreationResult:
        authority = self._authority_provider.validate_writer(
            scope=AuthorityScope(
                organization_id=command.scope.organization_id,
                operational_unit_id=command.scope.operational_unit_id,
                planning_date=command.scope.planning_date,
                timezone=command.scope.timezone,
            ),
            decision_id=command.authority_decision_id,
            fencing_token=command.fencing_token,
        )
        return self._service.create(
            command=command,
            publication=self._publication_provider.get(command.scope),
            authority=authority,
        )

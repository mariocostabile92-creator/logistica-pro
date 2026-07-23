from datetime import UTC, datetime
from uuid import uuid4

from app.api.dependencies.runtime_authority import get_authority_runtime
from app.domain.execution_intent import (
    ExecutionIntentService,
    ExecutionIntentValidator,
)
from app.repositories.execution_intent_repository import (
    ExecutionIntentRepositorySQL,
)
from app.runtime.execution_intent import (
    ExecutionIntentRuntime,
    SqlExecutionPublicationProvider,
)


_clock = lambda: datetime.now(UTC)
_execution_intent_runtime = ExecutionIntentRuntime(
    service=ExecutionIntentService(
        repository=ExecutionIntentRepositorySQL(),
        validator=ExecutionIntentValidator(),
        clock=_clock,
        identifier_factory=lambda: uuid4().hex,
    ),
    publication_provider=SqlExecutionPublicationProvider(),
    authority_provider=get_authority_runtime(),
    clock=_clock,
)


def get_execution_intent_runtime() -> ExecutionIntentRuntime:
    return _execution_intent_runtime

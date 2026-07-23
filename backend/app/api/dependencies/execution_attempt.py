from datetime import UTC, datetime
from uuid import uuid4

from app.domain.execution_attempt import (
    ExecutionAttemptService,
    ExecutionAttemptValidator,
)
from app.repositories.execution_attempt_repository import (
    ExecutionAttemptRepositorySQL,
)
from app.runtime.execution_attempt import ExecutionAttemptRuntime


_clock = lambda: datetime.now(UTC)
_execution_attempt_runtime = ExecutionAttemptRuntime(
    service=ExecutionAttemptService(
        repository=ExecutionAttemptRepositorySQL(),
        validator=ExecutionAttemptValidator(),
        clock=_clock,
        identifier_factory=lambda: uuid4().hex,
    ),
    clock=_clock,
)


def get_execution_attempt_runtime() -> ExecutionAttemptRuntime:
    return _execution_attempt_runtime

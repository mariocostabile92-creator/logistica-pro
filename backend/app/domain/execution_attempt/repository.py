from typing import Protocol

from app.domain.execution_attempt.models import (
    ExecutionAttempt,
    ExecutionAttemptHistory,
    ExecutionAttemptId,
    ExecutionAttemptScope,
    ExecutionAttemptSeriesScope,
)


class ExecutionAttemptRepositoryError(Exception):
    code = "EXECUTION_ATTEMPT_REPOSITORY_ERROR"


class ExecutionAttemptRepositoryConflictError(ExecutionAttemptRepositoryError):
    code = "EXECUTION_ATTEMPT_REPOSITORY_CONFLICT"


class ExecutionAttemptVersionError(ExecutionAttemptRepositoryError):
    code = "EXECUTION_ATTEMPT_VERSION_INVALID"


class ExecutionAttemptRepository(Protocol):
    def get_current(
        self,
        scope: ExecutionAttemptScope,
    ) -> ExecutionAttempt | None: ...

    def get_active(
        self,
        scope: ExecutionAttemptSeriesScope,
    ) -> ExecutionAttempt | None: ...

    def history(
        self,
        scope: ExecutionAttemptSeriesScope,
        *,
        limit: int = 100,
    ) -> ExecutionAttemptHistory: ...

    def next_attempt_number(
        self,
        scope: ExecutionAttemptSeriesScope,
    ) -> int: ...

    def append(self, attempt: ExecutionAttempt) -> None: ...

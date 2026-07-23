from typing import Protocol

from app.domain.execution_intent.models import (
    ExecutionIntent,
    ExecutionIntentId,
    ExecutionIntentKey,
    ExecutionIntentScope,
)


class ExecutionIntentRepositoryError(Exception):
    code = "EXECUTION_INTENT_REPOSITORY_ERROR"


class ExecutionIntentRepositoryConflictError(ExecutionIntentRepositoryError):
    code = "EXECUTION_INTENT_REPOSITORY_CONFLICT"


class ExecutionIntentVersionError(ExecutionIntentRepositoryError):
    code = "EXECUTION_INTENT_VERSION_INVALID"


class ExecutionIntentRepository(Protocol):
    def get_by_key(
        self,
        intent_key: ExecutionIntentKey,
    ) -> ExecutionIntent | None: ...

    def get_by_idempotency_key(
        self,
        *,
        organization_id: str,
        idempotency_key: str,
    ) -> ExecutionIntent | None: ...

    def list_for_scope(
        self,
        scope: ExecutionIntentScope,
    ) -> tuple[ExecutionIntent, ...]: ...

    def append(self, intent: ExecutionIntent) -> None: ...

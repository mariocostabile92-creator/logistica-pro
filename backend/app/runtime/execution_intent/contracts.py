from typing import Protocol

from app.domain.execution_intent import (
    ExecutionIntentScope,
    ExecutionPublicationReference,
)
from app.domain.runtime_authority import (
    AuthorityDecisionId,
    AuthorityResolutionResult,
    AuthorityScope,
)


class ExecutionPublicationProvider(Protocol):
    def get(
        self,
        scope: ExecutionIntentScope,
    ) -> ExecutionPublicationReference | None: ...


class ExecutionIntentAuthorityProvider(Protocol):
    def validate_writer(
        self,
        *,
        scope: AuthorityScope,
        decision_id: AuthorityDecisionId,
        fencing_token: int,
    ) -> AuthorityResolutionResult: ...

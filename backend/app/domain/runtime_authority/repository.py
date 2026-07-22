from typing import Protocol

from app.domain.runtime_authority.models import (
    AuthorityDecision,
    AuthorityDecisionId,
    AuthorityScope,
)


class AuthorityRepositoryError(Exception):
    code = "AUTHORITY_REPOSITORY_ERROR"


class AuthorityRepositoryConflictError(AuthorityRepositoryError):
    code = "AUTHORITY_REPOSITORY_CONFLICT"


class AuthorityFencingTokenError(AuthorityRepositoryError):
    code = "AUTHORITY_FENCING_TOKEN_INVALID"


class AuthorityVersionError(AuthorityRepositoryError):
    code = "AUTHORITY_VERSION_INVALID"


class AuthorityRepository(Protocol):
    def list_for_scope(
        self,
        scope: AuthorityScope,
    ) -> tuple[AuthorityDecision, ...]: ...

    def get_by_id(
        self,
        decision_id: AuthorityDecisionId,
    ) -> AuthorityDecision | None: ...

    def add(self, decision: AuthorityDecision) -> None: ...

    def latest_fencing_token(self, scope: AuthorityScope) -> int: ...

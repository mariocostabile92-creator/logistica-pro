from datetime import UTC, datetime

from app.domain.runtime_authority import (
    AuthorityResolver,
    AuthorityValidator,
)
from app.repositories.authority_repository import AuthorityRepositorySQL
from app.runtime.authority import AuthorityRuntimeService


_validator = AuthorityValidator()
_authority_runtime = AuthorityRuntimeService(
    repository=AuthorityRepositorySQL(),
    resolver=AuthorityResolver(_validator),
    validator=_validator,
    clock=lambda: datetime.now(UTC),
)


def get_authority_runtime() -> AuthorityRuntimeService:
    return _authority_runtime

from collections.abc import Callable
from datetime import datetime

from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDecisionId,
    AuthorityDiagnostics,
    AuthorityRepository,
    AuthorityResolutionResult,
    AuthorityResolutionState,
    AuthorityResolver,
    AuthorityScope,
    AuthorityStatus,
    AuthorityValidator,
    build_authority_diagnostics,
)
from app.runtime.authority.models import AuthorityRuntimeReport


class AuthorityRuntimeService:
    def __init__(
        self,
        *,
        repository: AuthorityRepository,
        resolver: AuthorityResolver,
        validator: AuthorityValidator,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._resolver = resolver
        self._validator = validator
        self._clock = clock

    def load(self, scope: AuthorityScope) -> tuple[AuthorityDecision, ...]:
        return self._repository.list_for_scope(scope)

    def validate(
        self,
        decision: AuthorityDecision,
        *,
        assessed_at: datetime | None = None,
    ) -> AuthorityStatus:
        return self._validator.effective_status(
            decision,
            assessed_at=assessed_at or self._clock(),
        )

    def resolve(
        self,
        scope: AuthorityScope,
        *,
        assessed_at: datetime | None = None,
    ) -> AuthorityResolutionResult:
        timestamp = assessed_at or self._clock()
        return self._resolver.resolve(
            scope=scope,
            decisions=self.load(scope),
            assessed_at=timestamp,
        )

    @staticmethod
    def diagnose(
        resolution: AuthorityResolutionResult,
    ) -> AuthorityDiagnostics:
        return build_authority_diagnostics(resolution)

    def report(
        self,
        scope: AuthorityScope,
        *,
        assessed_at: datetime | None = None,
    ) -> AuthorityRuntimeReport:
        timestamp = assessed_at or self._clock()
        resolution = self.resolve(scope, assessed_at=timestamp)
        return AuthorityRuntimeReport(
            decision=resolution.decision,
            resolution=resolution,
            diagnostics=self.diagnose(resolution),
            generated_at=timestamp,
        )

    def validate_writer(
        self,
        *,
        scope: AuthorityScope,
        decision_id: AuthorityDecisionId,
        fencing_token: int,
        assessed_at: datetime | None = None,
    ) -> AuthorityResolutionResult:
        timestamp = assessed_at or self._clock()
        resolution = self.resolve(scope, assessed_at=timestamp)
        decision = resolution.decision
        if resolution.state is AuthorityResolutionState.NO_WRITE:
            return resolution
        if decision is None or decision.decision_id != decision_id:
            return self._fencing_rejection(
                scope=scope,
                decision=decision,
                timestamp=timestamp,
                code="AUTHORITY_DECISION_MISMATCH",
                message="Authority decision non corrente.",
            )
        diagnostic = self._validator.validate_fencing_token(
            decision,
            provided_token=fencing_token,
        )
        if diagnostic is not None:
            return self._fencing_rejection(
                scope=scope,
                decision=decision,
                timestamp=timestamp,
                code=diagnostic.code,
                message=diagnostic.message,
            )
        return resolution

    @staticmethod
    def _fencing_rejection(
        *,
        scope: AuthorityScope,
        decision: AuthorityDecision | None,
        timestamp: datetime,
        code: str,
        message: str,
    ) -> AuthorityResolutionResult:
        return AuthorityResolutionResult(
            state=AuthorityResolutionState.NO_WRITE,
            scope=scope,
            decision=decision,
            reason_code=code,
            reason=message,
            assessed_at=timestamp,
        )

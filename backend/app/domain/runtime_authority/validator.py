from datetime import datetime

from app.domain.runtime_authority.models import (
    AuthorityDecision,
    AuthorityDiagnostic,
    AuthorityDiagnosticSeverity,
    AuthorityScope,
    AuthorityStatus,
)


class AuthorityValidator:
    def effective_status(
        self,
        decision: AuthorityDecision,
        *,
        assessed_at: datetime,
    ) -> AuthorityStatus:
        if assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware.")
        if decision.status is not AuthorityStatus.ACTIVE:
            return decision.status
        if assessed_at >= decision.valid_until:
            return AuthorityStatus.EXPIRED
        if assessed_at < decision.valid_from:
            return AuthorityStatus.INVALID
        return AuthorityStatus.ACTIVE

    def validate_scope(
        self,
        decision: AuthorityDecision,
        scope: AuthorityScope,
    ) -> AuthorityDiagnostic | None:
        if decision.scope.identity == scope.identity:
            return None
        return AuthorityDiagnostic(
            code="AUTHORITY_SCOPE_MISMATCH",
            severity=AuthorityDiagnosticSeverity.ERROR,
            message="Authority non coerente con lo scope richiesto.",
        )

    def validate_fencing_token(
        self,
        decision: AuthorityDecision,
        *,
        provided_token: int,
    ) -> AuthorityDiagnostic | None:
        if provided_token == decision.fencing_token:
            return None
        return AuthorityDiagnostic(
            code="STALE_FENCING_TOKEN",
            severity=AuthorityDiagnosticSeverity.ERROR,
            message="Fencing token obsoleto o non riconosciuto.",
        )

from app.domain.runtime_authority.models import (
    AuthorityDiagnostic,
    AuthorityDiagnostics,
    AuthorityDiagnosticSeverity,
    AuthorityResolutionResult,
    AuthorityResolutionState,
)


def build_authority_diagnostics(
    resolution: AuthorityResolutionResult,
) -> AuthorityDiagnostics:
    severity = (
        AuthorityDiagnosticSeverity.INFO
        if resolution.state is AuthorityResolutionState.WRITE_ALLOWED
        else AuthorityDiagnosticSeverity.WARNING
    )
    items = [
        AuthorityDiagnostic(
            code=resolution.reason_code,
            severity=severity,
            message=resolution.reason,
        )
    ]
    items.extend(
        AuthorityDiagnostic(
            code=conflict.code,
            severity=AuthorityDiagnosticSeverity.ERROR,
            message=conflict.message,
        )
        for conflict in resolution.conflicts
    )
    return AuthorityDiagnostics(
        items=tuple(items[:10]),
        generated_at=resolution.assessed_at,
    )

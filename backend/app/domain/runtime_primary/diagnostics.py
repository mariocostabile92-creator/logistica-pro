from app.domain.runtime_primary.models import (
    RuntimePrimaryDiagnostic,
    RuntimePrimaryDiagnostics,
    RuntimePrimaryDiagnosticSeverity,
    RuntimePrimaryValidationResult,
)


class RuntimePrimaryDiagnosticsBuilder:
    @staticmethod
    def from_validation(
        validation: RuntimePrimaryValidationResult,
    ) -> RuntimePrimaryDiagnostics:
        return RuntimePrimaryDiagnostics(
            items=tuple(
                RuntimePrimaryDiagnostic(
                    code=rule.code,
                    severity=(
                        RuntimePrimaryDiagnosticSeverity.INFO
                        if rule.passed
                        else RuntimePrimaryDiagnosticSeverity.ERROR
                    ),
                    message=rule.reason,
                    remediation_hint=(
                        None if rule.passed else rule.remediation_hint
                    ),
                )
                for rule in validation.rules
            ),
            generated_at=validation.evaluated_at,
        )

    @staticmethod
    def append(
        diagnostics: RuntimePrimaryDiagnostics,
        *,
        code: str,
        severity: RuntimePrimaryDiagnosticSeverity,
        message: str,
        remediation_hint: str | None = None,
    ) -> RuntimePrimaryDiagnostics:
        return RuntimePrimaryDiagnostics(
            items=(
                *diagnostics.items,
                RuntimePrimaryDiagnostic(
                    code=code,
                    severity=severity,
                    message=message,
                    remediation_hint=remediation_hint,
                ),
            ),
            generated_at=diagnostics.generated_at,
        )

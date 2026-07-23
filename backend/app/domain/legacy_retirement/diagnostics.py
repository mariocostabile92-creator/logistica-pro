from app.domain.legacy_retirement.models import (
    LegacyRetirementDiagnostic,
    LegacyRetirementDiagnostics,
    LegacyRetirementDiagnosticSeverity,
    LegacyRetirementValidationResult,
)


class LegacyRetirementDiagnosticsBuilder:
    @staticmethod
    def from_validation(
        validation: LegacyRetirementValidationResult,
    ) -> LegacyRetirementDiagnostics:
        failed = tuple(
            LegacyRetirementDiagnostic(
                code=item.code,
                severity=LegacyRetirementDiagnosticSeverity.ERROR,
                message=item.reason,
                remediation_hint=item.remediation_hint,
            )
            for item in validation.checklist
            if not item.passed
        )
        items = failed or (
            LegacyRetirementDiagnostic(
                code="RETIREMENT_CHECKLIST_PASS",
                severity=LegacyRetirementDiagnosticSeverity.INFO,
                message="Tutte le precondizioni risultano soddisfatte.",
            ),
        )
        return LegacyRetirementDiagnostics(
            items=items,
            generated_at=validation.evaluated_at,
        )

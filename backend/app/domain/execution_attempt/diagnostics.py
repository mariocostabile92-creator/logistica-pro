from app.domain.execution_attempt.models import (
    ExecutionAttemptDiagnostic,
    ExecutionAttemptDiagnostics,
    ExecutionAttemptDiagnosticSeverity,
    ExecutionAttemptValidationResult,
)


def build_execution_attempt_diagnostics(
    validation: ExecutionAttemptValidationResult,
) -> ExecutionAttemptDiagnostics:
    failed = tuple(rule for rule in validation.rules if not rule.passed)
    if not failed:
        items = (
            ExecutionAttemptDiagnostic(
                code="EXECUTION_ATTEMPT_PENDING",
                severity=ExecutionAttemptDiagnosticSeverity.INFO,
                message="Execution Attempt autorizzato e privo di effetti.",
            ),
        )
    else:
        items = tuple(
            ExecutionAttemptDiagnostic(
                code=rule.code,
                severity=ExecutionAttemptDiagnosticSeverity.ERROR,
                message=rule.reason,
            )
            for rule in failed[:12]
        )
    return ExecutionAttemptDiagnostics(
        items=items,
        generated_at=validation.evaluated_at,
    )

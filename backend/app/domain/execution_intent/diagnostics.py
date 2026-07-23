from app.domain.execution_intent.models import (
    ExecutionIntentDiagnostic,
    ExecutionIntentDiagnostics,
    ExecutionIntentDiagnosticSeverity,
    ExecutionIntentValidationResult,
)


def build_execution_intent_diagnostics(
    validation: ExecutionIntentValidationResult,
) -> ExecutionIntentDiagnostics:
    failed = tuple(rule for rule in validation.rules if not rule.passed)
    if not failed:
        items = (
            ExecutionIntentDiagnostic(
                code=validation.rules[0].code,
                severity=ExecutionIntentDiagnosticSeverity.INFO,
                message=validation.rules[0].reason,
            ),
        )
    else:
        items = tuple(
            ExecutionIntentDiagnostic(
                code=rule.code,
                severity=ExecutionIntentDiagnosticSeverity.ERROR,
                message=rule.reason,
            )
            for rule in failed[:12]
        )
    return ExecutionIntentDiagnostics(
        items=items,
        generated_at=validation.evaluated_at,
    )

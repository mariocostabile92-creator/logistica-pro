from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.execution_attempt import (
    ExecutionAttempt,
    ExecutionAttemptDiagnostics,
)


class ExecutionAttemptRuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt: ExecutionAttempt | None = None
    diagnostics: ExecutionAttemptDiagnostics
    generated_at: datetime

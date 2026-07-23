from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionIntentDiagnostics,
)


class ExecutionIntentRuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: ExecutionIntent | None = None
    diagnostics: ExecutionIntentDiagnostics
    generated_at: datetime

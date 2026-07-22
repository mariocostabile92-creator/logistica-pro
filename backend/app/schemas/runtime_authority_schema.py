from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDiagnostics,
    AuthorityResolutionResult,
)


class AuthorityRuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: AuthorityDecision | None = None
    resolution: AuthorityResolutionResult
    diagnostics: AuthorityDiagnostics
    generated_at: datetime

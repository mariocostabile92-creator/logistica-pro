from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.runtime_authority import (
    AuthorityDecision,
    AuthorityDiagnostics,
    AuthorityResolutionResult,
)


class AuthorityRuntimeReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: AuthorityDecision | None = None
    resolution: AuthorityResolutionResult
    diagnostics: AuthorityDiagnostics
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware.")
        return value

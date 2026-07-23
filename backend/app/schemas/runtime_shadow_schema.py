from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.runtime_shadow import (
    PlanningMismatch,
    PlanningParityReport,
    RuntimeShadowDiagnostics,
    RuntimeShadowMetrics,
    RuntimeShadowState,
)


class RuntimeShadowResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: RuntimeShadowState
    report: PlanningParityReport | None = None
    mismatches: tuple[PlanningMismatch, ...] = Field(default_factory=tuple)
    metrics: RuntimeShadowMetrics | None = None
    diagnostics: RuntimeShadowDiagnostics
    generated_at: datetime

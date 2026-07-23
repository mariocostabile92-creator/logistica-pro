from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.planning_runtime import (
    PlanningRuntimeOutputDiagnostics,
    PlanningRuntimeOutputStatus,
    PlanningRuntimeProducerMetrics,
    PlanningRuntimeSnapshot,
)


class PlanningRuntimeOutputResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: PlanningRuntimeOutputStatus
    snapshot: PlanningRuntimeSnapshot | None = None
    metrics: PlanningRuntimeProducerMetrics | None = None
    diagnostics: PlanningRuntimeOutputDiagnostics
    generated_at: datetime

from typing import Protocol

from app.domain.planning_runtime import (
    PlanningRuntimeProductionContext,
    PlanningRuntimeScope,
)


class PlanningRuntimeProductionProvider(Protocol):
    def get(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> PlanningRuntimeProductionContext | None: ...


class EmptyPlanningRuntimeProductionProvider:
    def get(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> PlanningRuntimeProductionContext | None:
        return None

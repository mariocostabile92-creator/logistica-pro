from typing import Protocol

from app.domain.planning_runtime import PlanningRuntimeScope
from app.domain.runtime_primary import (
    LegacyFallbackResult,
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryWriteResult,
)


class RuntimePrimaryContextProvider(Protocol):
    def get(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimePrimaryEvaluationContext | None: ...


class EmptyRuntimePrimaryContextProvider:
    def get(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimePrimaryEvaluationContext | None:
        return None


class BlockedRuntimePrimaryWriter:
    def write(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryWriteResult:
        raise RuntimeError(
            "Runtime Primary writer is not configured for this deployment."
        )


class BlockedLegacyFallback:
    def activate(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> LegacyFallbackResult:
        raise RuntimeError(
            "Legacy fallback is not configured for this deployment."
        )

from typing import Protocol

from app.domain.runtime_canary import (
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryScope,
)


class RuntimeCanaryContextProvider(Protocol):
    def get(
        self,
        *,
        scope: RuntimeCanaryScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimeCanaryEvaluationContext | None: ...


class EmptyRuntimeCanaryContextProvider:
    def get(
        self,
        *,
        scope: RuntimeCanaryScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimeCanaryEvaluationContext | None:
        return None

from typing import Protocol

from app.domain.runtime_primary.models import (
    LegacyFallbackResult,
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryWriteResult,
)


class RuntimePrimaryWriter(Protocol):
    def write(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryWriteResult: ...


class LegacyFallback(Protocol):
    def activate(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> LegacyFallbackResult: ...

from typing import Protocol

from app.domain.runtime_shadow import RuntimeShadowResult, RuntimeShadowScope


class RuntimeShadowResultProvider(Protocol):
    def get(
        self,
        *,
        scope: RuntimeShadowScope,
        publication_version: int,
    ) -> RuntimeShadowResult | None: ...


class EmptyRuntimeShadowResultProvider:
    def get(
        self,
        *,
        scope: RuntimeShadowScope,
        publication_version: int,
    ) -> RuntimeShadowResult | None:
        return None

from app.domain.planning_runtime import PlanningRuntimeScope
from app.domain.runtime_primary import (
    RuntimePrimaryEvaluationContext,
    RuntimePrimaryReport,
    RuntimePrimaryService,
)
from app.runtime.primary.contracts import RuntimePrimaryContextProvider


class RuntimePrimaryRuntime:
    def __init__(
        self,
        *,
        service: RuntimePrimaryService,
        provider: RuntimePrimaryContextProvider,
    ) -> None:
        self._service = service
        self._provider = provider

    def current(
        self,
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimePrimaryReport:
        context = self._provider.get(
            scope=scope,
            publication_id=publication_id,
            publication_version=publication_version,
        )
        if context is None:
            return self._service.unavailable(
                scope=scope,
                publication_id=publication_id,
                publication_version=publication_version,
                code="READINESS_CERTIFICATION_NO_GO",
                message=(
                    "Runtime Primary disabilitato: la certificazione corrente "
                    "e Level 0 / NO-GO."
                ),
            )
        if not self._request_matches_context(
            scope=scope,
            publication_id=publication_id,
            publication_version=publication_version,
            context=context,
        ):
            return self._service.unavailable(
                scope=scope,
                publication_id=publication_id,
                publication_version=publication_version,
                code="RUNTIME_PRIMARY_SCOPE_MISMATCH",
                message=(
                    "Il contesto Runtime Primary non appartiene allo scope "
                    "richiesto."
                ),
            )
        return self._service.assess(context)

    def apply(
        self,
        context: RuntimePrimaryEvaluationContext,
    ) -> RuntimePrimaryReport:
        return self._service.apply(context)

    @staticmethod
    def _request_matches_context(
        *,
        scope: PlanningRuntimeScope,
        publication_id: str,
        publication_version: int,
        context: RuntimePrimaryEvaluationContext,
    ) -> bool:
        return (
            context.scope == scope
            and context.publication.publication_id == publication_id
            and context.publication.publication_version
            == publication_version
        )

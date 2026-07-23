import hashlib
from collections.abc import Callable
from datetime import datetime

from app.domain.runtime_canary import (
    RuntimeCanaryEvaluationContext,
    RuntimeCanaryResult,
    RuntimeCanaryScope,
    RuntimeCanaryService,
    RuntimeCanarySession,
)
from app.runtime.canary.contracts import RuntimeCanaryContextProvider


class RuntimeCanaryRuntime:
    def __init__(
        self,
        *,
        service: RuntimeCanaryService,
        provider: RuntimeCanaryContextProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._provider = provider
        self._clock = clock

    def current(
        self,
        *,
        scope: RuntimeCanaryScope,
        publication_id: str,
        publication_version: int,
    ) -> RuntimeCanaryResult:
        context = self._provider.get(
            scope=scope,
            publication_id=publication_id,
            publication_version=publication_version,
        )
        if context is None:
            return self._service.unavailable(
                session=self._session(
                    scope=scope,
                    publication_id=publication_id,
                    publication_version=publication_version,
                    authority_decision="unavailable",
                ),
                code="CANARY_CONTEXT_NOT_AVAILABLE",
                message=(
                    "Contesto Canary non disponibile; Runtime resta osservatore."
                ),
            )
        if (
            context.session.scope != scope
            or context.session.publication_id != publication_id
            or context.session.publication_version != publication_version
        ):
            return self._service.unavailable(
                session=self._session(
                    scope=scope,
                    publication_id=publication_id,
                    publication_version=publication_version,
                    authority_decision="scope-mismatch",
                ),
                code="CANARY_REQUEST_SCOPE_MISMATCH",
                message="Il contesto Canary non appartiene allo scope richiesto.",
            )
        return self._service.evaluate(context)

    def evaluate(
        self,
        context: RuntimeCanaryEvaluationContext,
    ) -> RuntimeCanaryResult:
        return self._service.evaluate(context)

    def _session(
        self,
        *,
        scope: RuntimeCanaryScope,
        publication_id: str,
        publication_version: int,
        authority_decision: str,
    ) -> RuntimeCanarySession:
        started_at = self._clock()
        identity = "|".join(
            (
                scope.organization_id,
                scope.operational_unit_id,
                scope.planning_date.isoformat(),
                scope.timezone,
                publication_id,
                str(publication_version),
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        return RuntimeCanarySession(
            session_id=f"canary-{digest}",
            organization_id=scope.organization_id,
            operational_unit_id=scope.operational_unit_id,
            planning_date=scope.planning_date,
            timezone=scope.timezone,
            started_at=started_at,
            authority_decision=authority_decision,
            publication_id=publication_id,
            publication_version=publication_version,
        )

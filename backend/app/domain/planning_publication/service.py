from collections.abc import Callable
from datetime import datetime

from app.domain.planning_publication.fingerprint import (
    planning_publication_fingerprint,
)
from app.domain.planning_publication.models import (
    PlanningPublication,
    PlanningPublicationHistory,
    PlanningPublicationReport,
    PlanningPublicationResult,
    PlanningPublicationScope,
    PlanningPublicationState,
    PlanningPublicationValidationContext,
)
from app.domain.planning_publication.repository import (
    PlanningPublicationRepository,
)
from app.domain.planning_publication.validator import (
    PlanningPublicationValidator,
)


class PlanningPublicationService:
    def __init__(
        self,
        *,
        repository: PlanningPublicationRepository,
        validator: PlanningPublicationValidator,
        clock: Callable[[], datetime],
        identifier_factory: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._clock = clock
        self._identifier_factory = identifier_factory

    def get_current(
        self,
        scope: PlanningPublicationScope,
    ) -> PlanningPublication | None:
        return self._repository.get_current(scope)

    def history(
        self,
        scope: PlanningPublicationScope,
        *,
        limit: int = 25,
    ) -> PlanningPublicationHistory:
        return self._repository.get_history(scope, limit=limit)

    def validate(
        self,
        context: PlanningPublicationValidationContext,
    ) -> PlanningPublicationResult:
        return self._validator.validate(context)

    def report_existing(
        self,
        *,
        scope: PlanningPublicationScope,
        generated_at: datetime,
    ) -> PlanningPublicationReport | None:
        current = self.get_current(scope)
        if current is None:
            return None
        result = self._transition_result(
            current.validation,
            state=PlanningPublicationState.PUBLISHED,
            rationale=(
                "Confirmed Plan pubblicato come contratto immutabile. "
                "Nessuna esecuzione avviata."
            ),
        )
        return self._report(
            scope=scope,
            result=result,
            current=current,
            generated_at=generated_at,
        )

    def validation_report(
        self,
        context: PlanningPublicationValidationContext,
    ) -> PlanningPublicationReport:
        result = self.validate(context)
        return self._report(
            scope=context.scope,
            result=result,
            current=context.active_publication,
            generated_at=context.evaluated_at,
        )

    def publish(
        self,
        *,
        context: PlanningPublicationValidationContext,
        actor: str,
    ) -> PlanningPublicationReport:
        result = self.validate(context)
        if not result.can_publish:
            failed = self._transition_result(
                result,
                state=PlanningPublicationState.FAILED,
                rationale=(
                    "Publication rifiutata: "
                    + next(
                        rule.reason
                        for rule in result.rules
                        if not rule.passed
                    )
                ),
            )
            return self._report(
                scope=context.scope,
                result=failed,
                current=context.active_publication,
                generated_at=context.evaluated_at,
            )

        confirmation = context.confirmation
        if confirmation is None:
            raise RuntimeError("Validated publication context is incomplete.")
        published_at = self._clock()
        version = self._repository.next_version(context.scope)
        publication = PlanningPublication(
            publication_id=f"publication-{self._identifier_factory()}",
            scope=context.scope,
            version=version,
            confirmation_id=confirmation.confirmation_id,
            confirmation_version=confirmation.version,
            confirmation_fingerprint=confirmation.fingerprint,
            fingerprint=planning_publication_fingerprint(
                scope=context.scope,
                confirmation=confirmation,
                version=version,
            ),
            actor=actor,
            published_at=published_at,
            validation=result,
        )
        self._repository.add(publication)
        published_result = self._transition_result(
            result,
            state=PlanningPublicationState.PUBLISHED,
            rationale=(
                "Confirmed Plan pubblicato come contratto immutabile. "
                "Nessuna esecuzione avviata."
            ),
        )
        return self._report(
            scope=context.scope,
            result=published_result,
            current=publication,
            generated_at=published_at,
        )

    def _report(
        self,
        *,
        scope: PlanningPublicationScope,
        result: PlanningPublicationResult,
        current: PlanningPublication | None,
        generated_at: datetime,
    ) -> PlanningPublicationReport:
        return PlanningPublicationReport(
            state=result.state,
            result=result,
            current=current,
            history=self.history(scope, limit=5),
            generated_at=generated_at,
        )

    @staticmethod
    def _transition_result(
        result: PlanningPublicationResult,
        *,
        state: PlanningPublicationState,
        rationale: str,
    ) -> PlanningPublicationResult:
        return PlanningPublicationResult.model_validate(
            {
                **result.model_dump(),
                "state": state,
                "can_publish": False,
                "rationale": rationale,
            }
        )

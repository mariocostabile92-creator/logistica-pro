from collections.abc import Callable
from datetime import datetime

from app.domain.planning_confirmation.fingerprint import (
    planning_confirmation_fingerprint,
)
from app.domain.planning_confirmation.models import (
    PlanningConfirmation,
    PlanningConfirmationHistory,
    PlanningConfirmationReport,
    PlanningConfirmationResult,
    PlanningConfirmationScope,
    PlanningConfirmationState,
    PlanningConfirmationValidationContext,
)
from app.domain.planning_confirmation.repository import (
    PlanningConfirmationRepository,
)
from app.domain.planning_confirmation.validator import (
    PlanningConfirmationValidator,
)


class PlanningConfirmationService:
    def __init__(
        self,
        *,
        repository: PlanningConfirmationRepository,
        validator: PlanningConfirmationValidator,
        clock: Callable[[], datetime],
        identifier_factory: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._clock = clock
        self._identifier_factory = identifier_factory

    def get_current(
        self,
        scope: PlanningConfirmationScope,
    ) -> PlanningConfirmation | None:
        return self._repository.get_current(scope)

    def history(
        self,
        scope: PlanningConfirmationScope,
        *,
        limit: int = 25,
    ) -> PlanningConfirmationHistory:
        return self._repository.get_history(scope, limit=limit)

    def validate(
        self,
        context: PlanningConfirmationValidationContext,
    ) -> PlanningConfirmationResult:
        return self._validator.validate(context)

    def report_existing(
        self,
        *,
        scope: PlanningConfirmationScope,
        generated_at: datetime,
    ) -> PlanningConfirmationReport | None:
        current = self.get_current(scope)
        if current is None:
            return None
        result = self._transition_result(
            current.validation,
            state=PlanningConfirmationState.CONFIRMED,
            rationale="Draft congelato come Confirmed Plan immutabile.",
        )
        return self._report(
            scope=scope,
            result=result,
            current=current,
            generated_at=generated_at,
        )

    def validation_report(
        self,
        context: PlanningConfirmationValidationContext,
    ) -> PlanningConfirmationReport:
        result = self.validate(context)
        return self._report(
            scope=context.scope,
            result=result,
            current=context.active_confirmation,
            generated_at=context.evaluated_at,
        )

    def confirm(
        self,
        *,
        context: PlanningConfirmationValidationContext,
        actor: str,
    ) -> PlanningConfirmationReport:
        result = self.validate(context)
        if not result.can_confirm:
            rejected = self._transition_result(
                result,
                state=PlanningConfirmationState.REJECTED,
                rationale=(
                    "Conferma rifiutata: "
                    + next(
                        rule.reason
                        for rule in result.rules
                        if not rule.passed
                    )
                ),
            )
            return self._report(
                scope=context.scope,
                result=rejected,
                current=context.active_confirmation,
                generated_at=context.evaluated_at,
            )

        draft = context.draft
        envelope = context.envelope
        if draft is None or envelope is None:
            raise RuntimeError("Validated confirmation context is incomplete.")
        confirmed_at = self._clock()
        confirmation = PlanningConfirmation(
            confirmation_id=(
                f"confirmation-{self._identifier_factory()}"
            ),
            scope=context.scope,
            version=self._repository.next_version(context.scope),
            draft_id=draft.draft_id,
            draft_version=draft.version.number,
            draft_name=draft.metadata.name,
            draft_note=draft.metadata.note,
            readiness_status=context.readiness.status,
            readiness_score=context.readiness.score.value,
            envelope_version=envelope.version.value,
            envelope_fingerprint=envelope.fingerprint,
            fingerprint=planning_confirmation_fingerprint(
                scope=context.scope,
                draft=draft,
                envelope=envelope,
            ),
            actor=actor,
            confirmed_at=confirmed_at,
            validation=result,
        )
        self._repository.add(confirmation)
        confirmed_result = self._transition_result(
            result,
            state=PlanningConfirmationState.CONFIRMED,
            rationale="Draft congelato come Confirmed Plan immutabile.",
        )
        return self._report(
            scope=context.scope,
            result=confirmed_result,
            current=confirmation,
            generated_at=confirmed_at,
        )

    def _report(
        self,
        *,
        scope: PlanningConfirmationScope,
        result: PlanningConfirmationResult,
        current: PlanningConfirmation | None,
        generated_at: datetime,
    ) -> PlanningConfirmationReport:
        return PlanningConfirmationReport(
            state=result.state,
            result=result,
            current=current,
            history=self.history(scope, limit=5),
            generated_at=generated_at,
        )

    @staticmethod
    def _transition_result(
        result: PlanningConfirmationResult,
        *,
        state: PlanningConfirmationState,
        rationale: str,
    ) -> PlanningConfirmationResult:
        return PlanningConfirmationResult.model_validate(
            {
                **result.model_dump(),
                "state": state,
                "can_confirm": False,
                "rationale": rationale,
            }
        )

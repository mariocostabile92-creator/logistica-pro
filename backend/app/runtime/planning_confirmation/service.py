from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmationHistory,
    PlanningConfirmationReport,
    PlanningConfirmationScope,
    PlanningConfirmationService,
    PlanningConfirmationValidationContext,
)
from app.runtime.planning_confirmation.contracts import (
    PlanningConflictReviewer,
    PlanningDraftProvider,
    PlanningReadinessContextProvider,
)


class PlanningConfirmationRuntime:
    def __init__(
        self,
        *,
        service: PlanningConfirmationService,
        draft_provider: PlanningDraftProvider,
        readiness_provider: PlanningReadinessContextProvider,
        conflict_reviewer: PlanningConflictReviewer,
        actor: str = "private-beta",
    ) -> None:
        self._service = service
        self._draft_provider = draft_provider
        self._readiness_provider = readiness_provider
        self._conflict_reviewer = conflict_reviewer
        self._actor = actor

    def current(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        evaluated_at: datetime,
    ) -> PlanningConfirmationReport:
        scope = self._scope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )
        existing = self._service.report_existing(
            scope=scope,
            generated_at=evaluated_at,
        )
        if existing is not None:
            return existing
        context = self._context(
            scope=scope,
            requested_draft_id=None,
            requested_draft_version=None,
            evaluated_at=evaluated_at,
        )
        return self._service.validation_report(context)

    def validate(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        draft_id: str,
        draft_version: int,
        evaluated_at: datetime,
    ) -> PlanningConfirmationReport:
        context = self._context(
            scope=self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            ),
            requested_draft_id=draft_id,
            requested_draft_version=draft_version,
            evaluated_at=evaluated_at,
        )
        return self._service.validation_report(context)

    def confirm(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        draft_id: str,
        draft_version: int,
        evaluated_at: datetime,
    ) -> PlanningConfirmationReport:
        context = self._context(
            scope=self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            ),
            requested_draft_id=draft_id,
            requested_draft_version=draft_version,
            evaluated_at=evaluated_at,
        )
        return self._service.confirm(context=context, actor=self._actor)

    def history(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningConfirmationHistory:
        return self._service.history(
            self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            )
        )

    def _context(
        self,
        *,
        scope: PlanningConfirmationScope,
        requested_draft_id: str | None,
        requested_draft_version: int | None,
        evaluated_at: datetime,
    ) -> PlanningConfirmationValidationContext:
        draft_workspace = self._draft_provider.current(
            organization_id=scope.organization_id,
            operational_unit=scope.operational_unit,
            planning_date=scope.planning_date,
        )
        draft = draft_workspace.draft
        readiness_context = self._readiness_provider.evaluate_with_context(
            organization_id=scope.organization_id,
            operational_unit=scope.operational_unit,
            operation_date=scope.planning_date,
            evaluated_at=evaluated_at,
        )
        conflicts = self._conflict_reviewer.review(
            readiness=readiness_context.result,
            envelope=readiness_context.envelope,
        )
        return PlanningConfirmationValidationContext(
            scope=scope,
            requested_draft_id=(
                requested_draft_id
                if requested_draft_id is not None
                else draft.draft_id if draft is not None else None
            ),
            requested_draft_version=(
                requested_draft_version
                if requested_draft_version is not None
                else draft.version.number if draft is not None else None
            ),
            draft=draft,
            readiness=readiness_context.result,
            conflicts=conflicts,
            envelope=readiness_context.envelope,
            runtime_status=(
                readiness_context.composition_report.status.value
            ),
            runtime_compatible=(
                readiness_context.composition_report.compatibility.compatible
            ),
            active_confirmation=self._service.get_current(scope),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _scope(
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningConfirmationScope:
        return PlanningConfirmationScope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )

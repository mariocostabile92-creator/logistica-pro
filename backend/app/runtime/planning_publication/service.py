from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmation,
    PlanningConfirmationScope,
)
from app.domain.planning_publication import (
    PlanningPublicationHistory,
    PlanningPublicationReport,
    PlanningPublicationScope,
    PlanningPublicationService,
    PlanningPublicationValidationContext,
)
from app.runtime.planning_publication.contracts import (
    PlanningConfirmationProvider,
)


class PlanningPublicationRuntime:
    def __init__(
        self,
        *,
        service: PlanningPublicationService,
        confirmation_provider: PlanningConfirmationProvider,
        actor: str = "private-beta",
    ) -> None:
        self._service = service
        self._confirmation_provider = confirmation_provider
        self._actor = actor

    def current(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        evaluated_at: datetime,
    ) -> PlanningPublicationReport:
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
        confirmation = self._confirmation(scope)
        context = self._context(
            scope=scope,
            confirmation=confirmation,
            requested_confirmation_id=(
                confirmation.confirmation_id if confirmation else None
            ),
            requested_confirmation_version=(
                confirmation.version if confirmation else None
            ),
            requested_confirmation_fingerprint=(
                confirmation.fingerprint if confirmation else None
            ),
            evaluated_at=evaluated_at,
        )
        return self._service.validation_report(context)

    def validate(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        confirmation_id: str,
        confirmation_version: int,
        confirmation_fingerprint: str,
        evaluated_at: datetime,
    ) -> PlanningPublicationReport:
        scope = self._scope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )
        return self._service.validation_report(
            self._context(
                scope=scope,
                confirmation=self._confirmation(scope),
                requested_confirmation_id=confirmation_id,
                requested_confirmation_version=confirmation_version,
                requested_confirmation_fingerprint=confirmation_fingerprint,
                evaluated_at=evaluated_at,
            )
        )

    def publish(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        confirmation_id: str,
        confirmation_version: int,
        confirmation_fingerprint: str,
        evaluated_at: datetime,
    ) -> PlanningPublicationReport:
        scope = self._scope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )
        context = self._context(
            scope=scope,
            confirmation=self._confirmation(scope),
            requested_confirmation_id=confirmation_id,
            requested_confirmation_version=confirmation_version,
            requested_confirmation_fingerprint=confirmation_fingerprint,
            evaluated_at=evaluated_at,
        )
        return self._service.publish(context=context, actor=self._actor)

    def history(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningPublicationHistory:
        return self._service.history(
            self._scope(
                organization_id=organization_id,
                operational_unit=operational_unit,
                planning_date=planning_date,
            )
        )

    def _confirmation(
        self,
        scope: PlanningPublicationScope,
    ) -> PlanningConfirmation | None:
        return self._confirmation_provider.get_current(
            PlanningConfirmationScope(
                organization_id=scope.organization_id,
                operational_unit=scope.operational_unit,
                planning_date=scope.planning_date,
            )
        )

    def _context(
        self,
        *,
        scope: PlanningPublicationScope,
        confirmation: PlanningConfirmation | None,
        requested_confirmation_id: str | None,
        requested_confirmation_version: int | None,
        requested_confirmation_fingerprint: str | None,
        evaluated_at: datetime,
    ) -> PlanningPublicationValidationContext:
        runtime_rule = next(
            (
                rule
                for rule in confirmation.validation.rules
                if rule.code == "RUNTIME_COMPATIBLE"
            ),
            None,
        ) if confirmation else None
        operational_unit_valid = bool(
            confirmation
            and confirmation.scope.organization_id == scope.organization_id
            and (
                confirmation.scope.operational_unit.external_identifier
                == scope.operational_unit.external_identifier
            )
            and confirmation.scope.planning_date == scope.planning_date
        )
        return PlanningPublicationValidationContext(
            scope=scope,
            requested_confirmation_id=requested_confirmation_id,
            requested_confirmation_version=requested_confirmation_version,
            requested_confirmation_fingerprint=requested_confirmation_fingerprint,
            confirmation=confirmation,
            runtime_compatible=bool(runtime_rule and runtime_rule.passed),
            operational_unit_valid=operational_unit_valid,
            active_publication=self._service.get_current(scope),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _scope(
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningPublicationScope:
        return PlanningPublicationScope(
            organization_id=organization_id,
            operational_unit=operational_unit,
            planning_date=planning_date,
        )

from datetime import timedelta

from app.domain.planning_publication import (
    PlanningPublicationPolicy,
    PlanningPublicationScope,
    PlanningPublicationService,
    PlanningPublicationValidationContext,
    PlanningPublicationValidator,
)
from app.repositories.planning_confirmation_repository import (
    SqlPlanningConfirmationRepository,
)
from app.repositories.planning_publication_repository import (
    SqlPlanningPublicationRepository,
)
from app.runtime.planning_publication import PlanningPublicationRuntime
from planning_confirmation_helpers import (
    NOW,
    OPERATION_DATE,
    ORGANIZATION_ID,
    UNIT,
    Identifiers,
    confirmation_context,
    confirmation_service,
    create_draft,
    draft_service,
)


PUBLICATION_SCOPE = PlanningPublicationScope(
    organization_id=ORGANIZATION_ID,
    operational_unit=UNIT,
    planning_date=OPERATION_DATE,
)


def create_confirmation():
    drafts = draft_service()
    draft = create_draft(drafts)
    service = confirmation_service()
    report = service.confirm(
        context=confirmation_context(draft),
        actor="confirmation-author",
    )
    return report.current


def publication_service() -> PlanningPublicationService:
    return PlanningPublicationService(
        repository=SqlPlanningPublicationRepository(),
        validator=PlanningPublicationValidator(PlanningPublicationPolicy()),
        clock=lambda: NOW + timedelta(minutes=10),
        identifier_factory=Identifiers(),
    )


def publication_context(
    confirmation,
    *,
    service: PlanningPublicationService | None = None,
    runtime_compatible: bool = True,
    operational_unit_valid: bool = True,
) -> PlanningPublicationValidationContext:
    return PlanningPublicationValidationContext(
        scope=PUBLICATION_SCOPE,
        requested_confirmation_id=(
            confirmation.confirmation_id if confirmation else None
        ),
        requested_confirmation_version=(
            confirmation.version if confirmation else None
        ),
        requested_confirmation_fingerprint=(
            confirmation.fingerprint if confirmation else None
        ),
        confirmation=confirmation,
        runtime_compatible=runtime_compatible,
        operational_unit_valid=operational_unit_valid,
        active_publication=(
            service.get_current(PUBLICATION_SCOPE) if service else None
        ),
        evaluated_at=NOW + timedelta(minutes=6),
    )


def publication_runtime():
    confirmation = create_confirmation()
    runtime = PlanningPublicationRuntime(
        service=publication_service(),
        confirmation_provider=SqlPlanningConfirmationRepository(),
        actor="qa-publisher",
    )
    return runtime, confirmation

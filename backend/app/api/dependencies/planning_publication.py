from datetime import UTC, datetime
from uuid import uuid4

from app.domain.planning_publication import (
    PlanningPublicationPolicy,
    PlanningPublicationService,
    PlanningPublicationValidator,
)
from app.repositories.planning_confirmation_repository import (
    SqlPlanningConfirmationRepository,
)
from app.repositories.planning_publication_repository import (
    SqlPlanningPublicationRepository,
)
from app.runtime.planning_publication import PlanningPublicationRuntime


_publication_runtime = PlanningPublicationRuntime(
    service=PlanningPublicationService(
        repository=SqlPlanningPublicationRepository(),
        validator=PlanningPublicationValidator(PlanningPublicationPolicy()),
        clock=lambda: datetime.now(UTC),
        identifier_factory=lambda: uuid4().hex,
    ),
    confirmation_provider=SqlPlanningConfirmationRepository(),
)


def get_planning_publication_runtime() -> PlanningPublicationRuntime:
    return _publication_runtime

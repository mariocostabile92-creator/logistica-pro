from datetime import UTC, datetime
from uuid import uuid4

from app.api.dependencies.planning_drafts import get_planning_draft_runtime
from app.api.dependencies.planning_readiness import (
    get_planning_readiness_service,
)
from app.domain.planning_confirmation import (
    PlanningConfirmationPolicy,
    PlanningConfirmationService,
    PlanningConfirmationValidator,
)
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictEvaluator,
    PlanningConflictFormatter,
)
from app.repositories.planning_confirmation_repository import (
    SqlPlanningConfirmationRepository,
)
from app.runtime.planning_confirmation import PlanningConfirmationRuntime


_confirmation_runtime = PlanningConfirmationRuntime(
    service=PlanningConfirmationService(
        repository=SqlPlanningConfirmationRepository(),
        validator=PlanningConfirmationValidator(
            PlanningConfirmationPolicy()
        ),
        clock=lambda: datetime.now(UTC),
        identifier_factory=lambda: uuid4().hex,
    ),
    draft_provider=get_planning_draft_runtime(),
    readiness_provider=get_planning_readiness_service(),
    conflict_reviewer=PlanningConflictEngine(
        PlanningConflictEvaluator(PlanningConflictFormatter())
    ),
)


def get_planning_confirmation_runtime() -> PlanningConfirmationRuntime:
    return _confirmation_runtime

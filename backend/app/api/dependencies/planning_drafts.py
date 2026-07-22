from datetime import UTC, datetime
from uuid import uuid4

from app.domain.planning_drafts import PlanningDraftService
from app.repositories.planning_draft_repository import (
    SqlPlanningDraftRepository,
)
from app.runtime.planning_drafts import PlanningDraftRuntime


_draft_runtime = PlanningDraftRuntime(
    service=PlanningDraftService(
        repository=SqlPlanningDraftRepository(),
        clock=lambda: datetime.now(UTC),
        identifier_factory=lambda: uuid4().hex,
    )
)


def get_planning_draft_runtime() -> PlanningDraftRuntime:
    return _draft_runtime

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends

from app.api.dependencies.organization_scope import authenticated_organization_id
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


def get_tenant_planning_draft_runtime(
    organization_id: str = Depends(authenticated_organization_id),
) -> PlanningDraftRuntime:
    """Request-local repository: ID access is constrained by the session tenant."""
    return PlanningDraftRuntime(
        service=PlanningDraftService(
            repository=SqlPlanningDraftRepository(organization_id=organization_id),
            clock=lambda: datetime.now(UTC),
            identifier_factory=lambda: uuid4().hex,
        )
    )

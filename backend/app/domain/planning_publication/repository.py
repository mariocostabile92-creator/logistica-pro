from typing import Protocol

from app.domain.planning_publication.models import (
    PlanningPublication,
    PlanningPublicationHistory,
    PlanningPublicationScope,
)


class PlanningPublicationRepository(Protocol):
    def get_current(
        self,
        scope: PlanningPublicationScope,
    ) -> PlanningPublication | None: ...

    def get_history(
        self,
        scope: PlanningPublicationScope,
        *,
        limit: int = 100,
    ) -> PlanningPublicationHistory: ...

    def next_version(self, scope: PlanningPublicationScope) -> int: ...

    def add(self, publication: PlanningPublication) -> None: ...

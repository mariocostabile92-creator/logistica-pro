from typing import Protocol

from app.domain.planning_confirmation.models import (
    PlanningConfirmation,
    PlanningConfirmationHistory,
    PlanningConfirmationScope,
)


class PlanningConfirmationRepository(Protocol):
    def get_current(
        self,
        scope: PlanningConfirmationScope,
    ) -> PlanningConfirmation | None: ...

    def get_history(
        self,
        scope: PlanningConfirmationScope,
        *,
        limit: int = 100,
    ) -> PlanningConfirmationHistory: ...

    def next_version(self, scope: PlanningConfirmationScope) -> int: ...

    def add(self, confirmation: PlanningConfirmation) -> None: ...

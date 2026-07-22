from typing import Protocol

from app.domain.planning_confirmation import (
    PlanningConfirmation,
    PlanningConfirmationScope,
)


class PlanningConfirmationProvider(Protocol):
    def get_current(
        self,
        scope: PlanningConfirmationScope,
    ) -> PlanningConfirmation | None: ...

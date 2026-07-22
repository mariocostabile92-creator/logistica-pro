from datetime import date, datetime
from typing import Protocol

from app.domain.core_language import OperationalUnit
from app.runtime.planning_inputs import PlanningInputCompositionResult


class PlanningInputCompositionProvider(Protocol):
    def compose(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        composed_at: datetime,
    ) -> PlanningInputCompositionResult: ...

from datetime import date, datetime, timedelta
from typing import Protocol

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import PlanningInputSnapshot


class PlanningInputProducer(Protocol):
    def __call__(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        assessed_at: datetime,
        freshness_ttl: timedelta,
    ) -> PlanningInputSnapshot | None: ...

from collections import OrderedDict
from datetime import date, datetime, timedelta
from threading import Lock

from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictResult,
)
from app.runtime.planning_conflicts.contracts import (
    PlanningReadinessContextProvider,
)
from app.runtime.planning_conflicts.models import PlanningConflictReviewContext


CacheKey = tuple[str, str, date]


class PlanningConflictService:
    def __init__(
        self,
        *,
        readiness_provider: PlanningReadinessContextProvider,
        engine: PlanningConflictEngine,
        cache_ttl: timedelta = timedelta(seconds=2),
        max_cache_entries: int = 16,
    ) -> None:
        if cache_ttl <= timedelta(0):
            raise ValueError("cache_ttl must be positive.")
        if max_cache_entries < 1:
            raise ValueError("max_cache_entries must be positive.")
        self._readiness_provider = readiness_provider
        self._engine = engine
        self._cache_ttl = cache_ttl
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[
            CacheKey,
            PlanningConflictReviewContext,
        ] = OrderedDict()
        self._cache_lock = Lock()

    def review(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningConflictResult:
        return self.review_with_context(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            evaluated_at=evaluated_at,
        ).result

    def review_with_context(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningConflictReviewContext:
        key = (
            organization_id,
            operational_unit.external_identifier,
            operation_date,
        )
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                age = evaluated_at - cached.evaluated_at
                if timedelta(0) <= age <= self._cache_ttl:
                    self._cache.move_to_end(key)
                    return cached
                self._cache.pop(key, None)
            context = self._readiness_provider.evaluate_with_context(
                organization_id=organization_id,
                operational_unit=operational_unit,
                operation_date=operation_date,
                evaluated_at=evaluated_at,
            )
            result = self._engine.review(
                readiness=context.result,
                envelope=context.envelope,
            )
            review = PlanningConflictReviewContext(
                result=result,
                readiness=context.result,
                composition_report=context.composition_report,
                evaluated_at=evaluated_at,
            )
            self._cache[key] = review
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_entries:
                self._cache.popitem(last=False)
            return review

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

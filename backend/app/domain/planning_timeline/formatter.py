import hashlib
from collections.abc import Mapping
from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_timeline.models import (
    PlanningTimelineCategory,
    PlanningTimelineEvent,
    PlanningTimelineMetadata,
    PlanningTimelineSeverity,
)


def _metadata_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class PlanningTimelineFormatter:
    def format(
        self,
        *,
        timestamp: datetime,
        category: PlanningTimelineCategory,
        severity: PlanningTimelineSeverity,
        title: str,
        description: str,
        status: str,
        source: str,
        operational_unit: OperationalUnit,
        planning_date: date,
        reference: str | None = None,
        related_conflicts: tuple[str, ...] = (),
        related_readiness: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> PlanningTimelineEvent:
        identity = "|".join(
            (
                timestamp.isoformat(),
                category.value,
                source,
                reference or "",
                operational_unit.external_identifier,
                planning_date.isoformat(),
            )
        )
        event_id = "timeline-" + hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:16]
        metadata_items = tuple(
            PlanningTimelineMetadata(
                key=key,
                value=_metadata_value(value),
            )
            for key, value in sorted((metadata or {}).items())
            if value is not None and _metadata_value(value)
        )
        return PlanningTimelineEvent(
            id=event_id,
            timestamp=timestamp,
            category=category,
            severity=severity,
            title=title,
            description=description,
            status=status,
            source=source,
            operational_unit=operational_unit,
            planning_date=planning_date,
            reference=reference,
            related_conflicts=related_conflicts,
            related_readiness=related_readiness,
            metadata=metadata_items,
        )

from datetime import datetime, timedelta

from app.domain.planning_timeline.models import (
    PlanningTimelineEvent,
    PlanningTimelineGroup,
)


_GROUPS = (
    ("LAST_HOUR", "Ultima ora"),
    ("TODAY", "Oggi"),
    ("OLDER", "Più vecchi"),
)


def sort_planning_timeline_events(
    events: tuple[PlanningTimelineEvent, ...],
) -> tuple[PlanningTimelineEvent, ...]:
    return tuple(
        sorted(
            events,
            key=lambda item: (item.timestamp, item.id),
            reverse=True,
        )[:100]
    )


def group_planning_timeline_events(
    events: tuple[PlanningTimelineEvent, ...],
    *,
    evaluated_at: datetime,
) -> tuple[PlanningTimelineGroup, ...]:
    last_hour = evaluated_at - timedelta(hours=1)
    grouped: dict[str, list[str]] = {key: [] for key, _ in _GROUPS}
    for event in events:
        if event.timestamp >= last_hour:
            key = "LAST_HOUR"
        elif event.timestamp.date() == evaluated_at.date():
            key = "TODAY"
        else:
            key = "OLDER"
        grouped[key].append(event.id)
    return tuple(
        PlanningTimelineGroup(
            key=key,
            label=label,
            event_count=len(grouped[key]),
            event_ids=tuple(grouped[key]),
        )
        for key, label in _GROUPS
        if grouped[key]
    )

from app.domain.planning_conflicts.models import (
    PlanningConflict,
    PlanningConflictGroup,
    PlanningConflictSeverity,
)


SEVERITY_RANK = {
    PlanningConflictSeverity.INFO: 0,
    PlanningConflictSeverity.LOW: 1,
    PlanningConflictSeverity.MEDIUM: 2,
    PlanningConflictSeverity.HIGH: 3,
    PlanningConflictSeverity.CRITICAL: 4,
}


def sort_planning_conflicts(
    conflicts: tuple[PlanningConflict, ...],
) -> tuple[PlanningConflict, ...]:
    return tuple(
        sorted(
            conflicts,
            key=lambda item: (
                not item.blocking,
                -SEVERITY_RANK[item.severity],
                item.category.value,
                item.code,
                item.id,
            ),
        )
    )


def group_planning_conflicts(
    conflicts: tuple[PlanningConflict, ...],
) -> tuple[PlanningConflictGroup, ...]:
    grouped: dict[object, list[PlanningConflict]] = {}
    for conflict in conflicts:
        grouped.setdefault(conflict.category, []).append(conflict)
    groups = []
    for category, items in grouped.items():
        ordered = sort_planning_conflicts(tuple(items))
        highest = max(ordered, key=lambda item: SEVERITY_RANK[item.severity])
        groups.append(
            PlanningConflictGroup(
                category=category,
                label=category.value.replace("_", " ").title(),
                total_conflicts=len(ordered),
                total_blocking=sum(item.blocking for item in ordered),
                highest_severity=highest.severity,
                conflict_ids=tuple(item.id for item in ordered),
            )
        )
    return tuple(
        sorted(
            groups,
            key=lambda item: (
                item.total_blocking == 0,
                -SEVERITY_RANK[item.highest_severity],
                item.category.value,
            ),
        )
    )

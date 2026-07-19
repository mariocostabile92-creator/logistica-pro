from app.domain.conflict_types import ConflictSeverity
from app.domain.operations_engine import OperationalCapacity, OperationalIssue, OperationalSummary


def build_summary(
    capacity: OperationalCapacity,
    issues: list[OperationalIssue],
) -> OperationalSummary:
    return OperationalSummary(
        routes=capacity.routes,
        drivers=capacity.drivers,
        physical_vehicles=capacity.physical_vehicles,
        operational_vehicles=capacity.operational_vehicles,
        reserve_vehicles=capacity.reserve_vehicles,
        blocked_vehicles=capacity.blocked_vehicles,
        issues_count=len(issues),
        critical_issues=sum(
            1 for issue in issues if issue.severity == ConflictSeverity.CRITICAL
        ),
        warning_issues=sum(
            1 for issue in issues if issue.severity == ConflictSeverity.WARNING
        ),
        info_issues=sum(
            1 for issue in issues if issue.severity == ConflictSeverity.INFO
        ),
    )

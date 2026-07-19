from app.domain.normalized_models import (
    NormalizedFleetRow,
    NormalizedPlanningRow,
    OperationConflict,
)
from app.domain.operations_engine import OperationalIssue, OperationsDashboard
from app.repositories.import_repository import get_latest_import
from app.repositories.operations_repository import (
    get_latest_operation_snapshot,
    save_operation_snapshot,
)
from app.schemas.operation_schema import AnalyzeResponse, OperationSummary
from app.services.capacity_service import calculate_capacity
from app.services.conflict_service import detect_conflicts
from app.services.readiness_service import calculate_readiness
from app.services.summary_service import build_summary
from app.utils.date_utils import utc_now_iso


class OperationsDataUnavailableError(ValueError):
    pass


def _to_issue(conflict: OperationConflict) -> OperationalIssue:
    return OperationalIssue(
        code=conflict.code,
        severity=conflict.severity,
        description=conflict.message,
        reason=conflict.reason or "La regola operativa associata al problema non è soddisfatta.",
        entity_ref=conflict.entity_ref,
        row_number=conflict.row_number,
        suggested_action=conflict.suggested_action,
    )


def evaluate_operations(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
    reserve_threshold: int = 1,
    recognized_operational_units: set[str] | None = None,
) -> OperationsDashboard:
    conflicts = detect_conflicts(
        planning_rows,
        fleet_rows,
        reserve_threshold=reserve_threshold,
        recognized_operational_units=recognized_operational_units,
    )
    issues = [_to_issue(conflict) for conflict in conflicts]
    capacity = calculate_capacity(planning_rows, fleet_rows)
    summary = build_summary(capacity, issues)
    readiness = calculate_readiness(capacity, issues, reserve_threshold)

    return OperationsDashboard(
        generated_at=utc_now_iso(),
        summary=summary,
        issues=issues,
        capacity=capacity,
        readiness=readiness,
    )


def evaluate_latest_operations(
    reserve_threshold: int = 1,
    recognized_operational_units: set[str] | None = None,
) -> OperationsDashboard:
    planning_import = get_latest_import("planning")
    fleet_import = get_latest_import("fleet")
    if not planning_import:
        raise OperationsDataUnavailableError("Nessun planning importato.")
    if not fleet_import:
        raise OperationsDataUnavailableError("Nessun parco auto importato.")

    snapshot = get_latest_operation_snapshot()
    if (
        snapshot
        and snapshot["planning_import_id"] == planning_import["id"]
        and snapshot["fleet_import_id"] == fleet_import["id"]
        and snapshot["reserve_threshold"] == reserve_threshold
    ):
        dashboard = OperationsDashboard.model_validate(snapshot["payload"])
        dashboard.analysis_id = snapshot["id"]
        return dashboard

    planning_rows = [
        NormalizedPlanningRow.model_validate(row)
        for row in planning_import["normalized_rows"]
    ]
    fleet_rows = [
        NormalizedFleetRow.model_validate(row)
        for row in fleet_import["normalized_rows"]
    ]
    dashboard = evaluate_operations(
        planning_rows,
        fleet_rows,
        reserve_threshold,
        recognized_operational_units,
    )
    dashboard.analysis_id = save_operation_snapshot(
        dashboard=dashboard.model_dump(mode="json", exclude={"analysis_id"}),
        planning_import_id=planning_import["id"],
        fleet_import_id=fleet_import["id"],
        reserve_threshold=reserve_threshold,
    )
    return dashboard


def dashboard_to_legacy_analysis(dashboard: OperationsDashboard) -> AnalyzeResponse:
    summary = dashboard.summary
    return AnalyzeResponse(
        summary=OperationSummary(
            routes=summary.routes,
            drivers=summary.drivers,
            operational_vehicles=summary.operational_vehicles,
            reserve_vehicles=summary.reserve_vehicles,
            critical_conflicts=summary.critical_issues,
            warnings=summary.warning_issues,
        ),
        conflicts=[
            OperationConflict(
                code=issue.code,
                severity=issue.severity.value,
                message=issue.description,
                reason=issue.reason,
                entity_ref=issue.entity_ref,
                row_number=issue.row_number,
                suggested_action=issue.suggested_action,
            )
            for issue in dashboard.issues
        ],
    )

from app.domain.normalized_models import (
    NormalizedFleetRow,
    NormalizedPlanningRow,
    OperationConflict,
)
from app.repositories.import_repository import (
    get_latest_analysis,
    get_latest_import,
    save_analysis,
)
from app.schemas.operation_schema import AnalyzeRequest, AnalyzeResponse
from app.services.operations_engine import (
    OperationsDataUnavailableError,
    dashboard_to_legacy_analysis,
    evaluate_operations,
)


class OperationsAnalysisNotFoundError(LookupError):
    pass


def run_analysis(
    request: AnalyzeRequest,
    recognized_operational_units: set[str] | None = None,
) -> AnalyzeResponse:
    planning_import = (
        get_latest_import("planning")
        if request.planning_rows is None
        else None
    )
    fleet_import = (
        get_latest_import("fleet")
        if request.fleet_rows is None
        else None
    )
    if request.planning_rows is None and not planning_import:
        raise OperationsDataUnavailableError("Nessun planning importato.")
    if request.fleet_rows is None and not fleet_import:
        raise OperationsDataUnavailableError("Nessun parco auto importato.")

    planning_rows_data = request.planning_rows or planning_import["normalized_rows"]
    fleet_rows_data = request.fleet_rows or fleet_import["normalized_rows"]
    planning_rows = [
        NormalizedPlanningRow.model_validate(row)
        for row in planning_rows_data
    ]
    fleet_rows = [
        NormalizedFleetRow.model_validate(row)
        for row in fleet_rows_data
    ]
    dashboard = evaluate_operations(
        planning_rows,
        fleet_rows,
        reserve_threshold=request.reserve_threshold,
        recognized_operational_units=recognized_operational_units,
    )
    response = dashboard_to_legacy_analysis(dashboard)
    response.analysis_id = save_analysis(
        response.summary.model_dump(),
        [conflict.model_dump() for conflict in response.conflicts],
    )
    return response


def get_latest_analysis_response() -> AnalyzeResponse:
    analysis = get_latest_analysis()
    if not analysis:
        raise OperationsAnalysisNotFoundError(
            "Nessuna analisi disponibile."
        )
    return AnalyzeResponse(
        analysis_id=analysis["id"],
        summary=analysis["summary"],
        conflicts=[
            OperationConflict.model_validate(item)
            for item in analysis["conflicts"]
        ],
    )

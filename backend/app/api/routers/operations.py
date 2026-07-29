from fastapi import APIRouter, HTTPException, Query

from app.adapters.registry import get_active_tabular_import_adapter
from app.domain.operations_engine import (
    OperationalCapacity,
    OperationalIssue,
    OperationalReadiness,
    OperationsDashboard,
)
from app.schemas.operation_schema import AnalyzeRequest, AnalyzeResponse
from app.services.operations_analysis_service import (
    OperationsAnalysisNotFoundError,
    get_latest_analysis_response,
    run_analysis,
)
from app.services.operations_engine import (
    OperationsDataUnavailableError,
    evaluate_latest_operations,
)


router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest | None = None) -> AnalyzeResponse:
    try:
        return run_analysis(
            request or AnalyzeRequest(),
            recognized_operational_units=(
                get_active_tabular_import_adapter()
                .recognized_operational_units()
            ),
        )
    except OperationsDataUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/latest", response_model=AnalyzeResponse)
def latest() -> AnalyzeResponse:
    try:
        return get_latest_analysis_response()
    except OperationsAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _latest_dashboard(reserve_threshold: int) -> OperationsDashboard:
    try:
        return evaluate_latest_operations(
            reserve_threshold,
            recognized_operational_units=(
                get_active_tabular_import_adapter()
                .recognized_operational_units()
            ),
        )
    except OperationsDataUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dashboard", response_model=OperationsDashboard)
def dashboard(
    reserve_threshold: int = Query(default=1, ge=0, le=1000),
) -> OperationsDashboard:
    return _latest_dashboard(reserve_threshold)


@router.get("/issues", response_model=list[OperationalIssue])
def issues(
    reserve_threshold: int = Query(default=1, ge=0, le=1000),
) -> list[OperationalIssue]:
    return _latest_dashboard(reserve_threshold).issues


@router.get("/capacity", response_model=OperationalCapacity)
def capacity(
    reserve_threshold: int = Query(default=1, ge=0, le=1000),
) -> OperationalCapacity:
    return _latest_dashboard(reserve_threshold).capacity


@router.get("/readiness", response_model=OperationalReadiness)
def readiness(
    reserve_threshold: int = Query(default=1, ge=0, le=1000),
) -> OperationalReadiness:
    return _latest_dashboard(reserve_threshold).readiness

from fastapi import APIRouter, HTTPException, Query, Response

from app.domain.assignment_models import Assignment
from app.schemas.assignment_schema import PatchAssignmentRequest
from app.schemas.planning_event_schema import (
    ApplyEventResponse,
    PlanningEventRequest,
    SimulateEventResponse,
)
from app.schemas.planning_schema import (
    GeneratePlanningRequest,
    PlanningHistoryResponse,
    PlanningResponse,
    RecalculatePlanningRequest,
)
from app.services.manual_assignment_service import (
    AssignmentValidationError,
    patch_assignment,
)
from app.services.exception_simulation_service import (
    EventSimulationError,
    apply_event,
    simulate_event,
)
from app.services.planning_export_service import export_planning_csv
from app.services.planning_generation_service import (
    PlanningNotFoundError,
    generate_planning,
    get_latest_planning_bundle,
    get_planning_bundle,
)
from app.services.planning_recalculation_service import recalculate_planning
from app.services.planning_validation_service import PlanningValidationError


router = APIRouter(prefix="/api/planning", tags=["planning"])


def _validation_http_error(exc: PlanningValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": exc.code,
            "message": str(exc),
            "conflicts": [
                item.model_dump(mode="json") for item in exc.conflicts
            ],
        },
    )


@router.post("/generate", response_model=PlanningResponse)
def generate(request: GeneratePlanningRequest) -> PlanningResponse:
    try:
        bundle = generate_planning(request)
        return PlanningResponse.model_validate(bundle.model_dump(mode="json"))
    except PlanningValidationError as exc:
        raise _validation_http_error(exc) from exc


@router.get("/latest", response_model=PlanningResponse)
def latest() -> PlanningResponse:
    try:
        bundle = get_latest_planning_bundle()
        return PlanningResponse.model_validate(bundle.model_dump(mode="json"))
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/assignments/{assignment_id}", response_model=Assignment)
def update_assignment(
    assignment_id: int,
    request: PatchAssignmentRequest,
) -> Assignment:
    try:
        return patch_assignment(assignment_id, request)
    except AssignmentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{planning_id}", response_model=PlanningResponse)
def get_planning(planning_id: int) -> PlanningResponse:
    try:
        bundle = get_planning_bundle(planning_id)
        return PlanningResponse.model_validate(bundle.model_dump(mode="json"))
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{planning_id}/recalculate", response_model=PlanningResponse)
def recalculate(
    planning_id: int,
    request: RecalculatePlanningRequest | None = None,
) -> PlanningResponse:
    try:
        bundle = recalculate_planning(
            planning_id,
            request or RecalculatePlanningRequest(),
        )
        return PlanningResponse.model_validate(bundle.model_dump(mode="json"))
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanningValidationError as exc:
        raise _validation_http_error(exc) from exc


@router.post(
    "/{planning_id}/simulate-event",
    response_model=SimulateEventResponse,
)
def simulate(
    planning_id: int,
    request: PlanningEventRequest,
) -> SimulateEventResponse:
    try:
        simulation = simulate_event(planning_id, request)
        return SimulateEventResponse.model_validate(
            simulation.model_dump(mode="json")
        )
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EventSimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{planning_id}/apply-event",
    response_model=ApplyEventResponse,
)
def apply(
    planning_id: int,
    request: PlanningEventRequest,
) -> ApplyEventResponse:
    try:
        bundle, event, diff = apply_event(planning_id, request)
        return ApplyEventResponse(
            planning=bundle.model_dump(mode="json"),
            event=event.model_dump(mode="json"),
            diff=diff.model_dump(mode="json"),
            version=bundle.planning.version,
        )
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EventSimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{planning_id}/history",
    response_model=PlanningHistoryResponse,
)
def history(planning_id: int) -> PlanningHistoryResponse:
    try:
        bundle = get_planning_bundle(planning_id)
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanningHistoryResponse(
        planning_id=planning_id,
        versions=bundle.history["versions"],
        events=bundle.history["events"],
    )


@router.get("/{planning_id}/export")
def export(
    planning_id: int,
    format: str = Query(default="csv", pattern="^csv$"),
) -> Response:
    try:
        content = export_planning_csv(planning_id)
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="planning-operativo-{planning_id}.csv"'
            )
        },
    )

from fastapi import APIRouter, HTTPException, status

from app.plugins.fleet.application.asset_service import (
    AssetNotFoundError,
    AssetValidationError,
    add_document,
    create_asset,
    get_asset,
    list_assets,
    list_events,
    observe_availability,
    save_profile,
    update_asset,
)
from app.plugins.fleet.domain.errors import AssetIdentifierConflictError
from app.plugins.fleet.domain.models import Asset, AssetDocument, FleetAssetProfile
from app.plugins.fleet.interfaces.schemas import (
    AssetCreateRequest,
    AssetDocumentCreateRequest,
    AssetEventsResponse,
    AssetListResponse,
    AssetUpdateRequest,
    AvailabilityObservationRequest,
    FleetAssetProfileRequest,
)
from app.workspace.status_service import (
    DemoWorkspaceResetRequiredError,
    ensure_real_data_write_allowed,
)


router = APIRouter(
    prefix="/api/plugins/fleet/v1",
    tags=["fleet-plugin-v1"],
)


def _not_found(exc: AssetNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/assets", response_model=AssetListResponse)
def assets() -> AssetListResponse:
    return AssetListResponse(items=list_assets())


@router.put(
    "/assets/{asset_id}/profile",
    response_model=FleetAssetProfile,
)
def asset_profile(
    asset_id: int,
    request: FleetAssetProfileRequest,
) -> FleetAssetProfile:
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    contract_type = values["contract_type"]
    if contract_type == "lungo_termine":
        values["daily_cost"] = None
    elif contract_type == "breve_termine":
        values["monthly_fee"] = None
    elif contract_type == "proprieta":
        values["monthly_fee"] = None
        values["daily_cost"] = None
    try:
        return save_profile(asset_id, values, actor)
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/assets",
    response_model=Asset,
    status_code=status.HTTP_201_CREATED,
)
def create(request: AssetCreateRequest) -> Asset:
    try:
        ensure_real_data_write_allowed()
        return create_asset(
            request.model_dump(exclude={"actor"}),
            actor=request.actor,
        )
    except AssetIdentifierConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DemoWorkspaceResetRequiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_WORKSPACE_RESET_REQUIRED",
                "message": str(exc),
            },
        ) from exc


@router.get("/assets/{asset_id}", response_model=Asset)
def detail(asset_id: int) -> Asset:
    try:
        return get_asset(asset_id)
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/assets/{asset_id}", response_model=Asset)
def update(asset_id: int, request: AssetUpdateRequest) -> Asset:
    try:
        return update_asset(
            asset_id,
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            actor=request.actor,
        )
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc
    except AssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssetIdentifierConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/availability", response_model=Asset)
def availability(
    asset_id: int,
    request: AvailabilityObservationRequest,
) -> Asset:
    try:
        return observe_availability(
            asset_id,
            availability=request.availability,
            note=request.note,
            actor=request.actor,
        )
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/assets/{asset_id}/documents",
    response_model=AssetDocument,
    status_code=status.HTTP_201_CREATED,
)
def document(
    asset_id: int,
    request: AssetDocumentCreateRequest,
) -> AssetDocument:
    try:
        return add_document(
            asset_id,
            request.model_dump(exclude={"actor"}),
            actor=request.actor,
        )
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/assets/{asset_id}/events",
    response_model=AssetEventsResponse,
)
def events(asset_id: int) -> AssetEventsResponse:
    try:
        return AssetEventsResponse(items=list_events(asset_id))
    except AssetNotFoundError as exc:
        raise _not_found(exc) from exc

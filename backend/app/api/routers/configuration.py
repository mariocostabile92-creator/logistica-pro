from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies.organization_scope import (
    authenticated_organization_id,
    authorize_organization_scope,
)

from app.core.configuration.models import Configuration, ConfigurationScope
from app.core.configuration.service import (
    ConfigurationValidationError,
    create_configuration_version,
    get_current_configuration,
    list_configuration_versions,
    validate_configuration,
)
from app.schemas.configuration_schema import (
    ConfigurationValidationRequest,
    ConfigurationValidationResponse,
    ConfigurationVersionCreateRequest,
    ConfigurationVersionsResponse,
)


router = APIRouter(
    prefix="/api/configuration/v1",
    tags=["configuration-engine-v1"],
)


def _scope(
    organization_id: str,
    operational_unit_id: str | None,
    adapter_id: str | None,
    tenant_id: str,
) -> ConfigurationScope:
    return ConfigurationScope(
        organization_id=authorize_organization_scope(organization_id, tenant_id),
        operational_unit_id=operational_unit_id,
        adapter_id=adapter_id,
    )


@router.get("/current", response_model=Configuration)
def current(
    organization_id: str = Query(default="default", min_length=1),
    operational_unit_id: str | None = Query(default=None),
    adapter_id: str | None = Query(default=None),
    tenant_id: str = Depends(authenticated_organization_id),
) -> Configuration:
    return get_current_configuration(
        _scope(
            organization_id,
            operational_unit_id,
            adapter_id,
            tenant_id,
        )
    )


@router.get("/versions", response_model=ConfigurationVersionsResponse)
def versions(
    organization_id: str = Query(default="default", min_length=1),
    operational_unit_id: str | None = Query(default=None),
    adapter_id: str | None = Query(default=None),
    tenant_id: str = Depends(authenticated_organization_id),
) -> ConfigurationVersionsResponse:
    scope = _scope(
        organization_id,
        operational_unit_id,
        adapter_id,
        tenant_id,
    )
    return ConfigurationVersionsResponse(
        scope=scope,
        items=list_configuration_versions(scope),
    )


@router.post(
    "/validate",
    response_model=ConfigurationValidationResponse,
)
def validate(
    request: ConfigurationValidationRequest,
    tenant_id: str = Depends(authenticated_organization_id),
) -> ConfigurationValidationResponse:
    result = validate_configuration(
        [
            section.model_dump(mode="json")
            for section in request.sections
        ],
        _scope(
            request.organization_id,
            request.operational_unit_id,
            request.adapter_id,
            tenant_id,
        ),
    )
    return ConfigurationValidationResponse(**result.model_dump())


@router.post(
    "/versions",
    response_model=Configuration,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    request: ConfigurationVersionCreateRequest,
    tenant_id: str = Depends(authenticated_organization_id),
) -> Configuration:
    try:
        return create_configuration_version(
            scope=_scope(
                request.organization_id,
                request.operational_unit_id,
                request.adapter_id,
                tenant_id,
            ),
            raw_sections=[
                section.model_dump(mode="json")
                for section in request.sections
            ],
            created_by=request.created_by,
            note=request.note,
            valid_from=request.valid_from,
        )
    except ConfigurationValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "errors": exc.errors,
            },
        ) from exc

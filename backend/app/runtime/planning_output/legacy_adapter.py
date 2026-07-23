from datetime import datetime

from app.domain.core_language import (
    AssetReference,
    HumanResource,
    ResourceAvailability,
    ResourceKind,
)
from app.domain.execution_intent import ExecutionPublicationReference
from app.domain.planning_inputs import PlanningResourceCapability
from app.domain.planning_models import PlanningBundle
from app.domain.planning_runtime import (
    PlanningRuntimeAssignment,
    PlanningRuntimeOutputVersion,
    PlanningRuntimeProducerInput,
    PlanningRuntimeScope,
)


class LegacyPlanningOutputAdapter:
    def adapt(
        self,
        *,
        bundle: PlanningBundle,
        publication: ExecutionPublicationReference,
        organization_id: str,
        operational_unit_id: str,
        timezone: str,
        input_fingerprint: str,
        configuration_version: str,
        evaluated_at: datetime,
        capabilities: tuple[PlanningResourceCapability, ...] = (),
    ) -> PlanningRuntimeProducerInput:
        planning_date = bundle.planning.operation_date
        if planning_date != publication.planning_date.isoformat():
            raise ValueError("Legacy Planning and Publication dates differ.")

        resources: dict[str, HumanResource] = {}
        fleet: dict[str, AssetReference] = {}
        assignments: list[PlanningRuntimeAssignment] = []
        availability: dict[
            tuple[ResourceKind, str],
            ResourceAvailability,
        ] = {}

        for assignment in bundle.assignments:
            if assignment.driver_id:
                resources.setdefault(
                    assignment.driver_id,
                    HumanResource(
                        external_identifier=assignment.driver_id,
                        display_name=assignment.driver_name,
                    ),
                )
                availability[(ResourceKind.HUMAN_RESOURCE, assignment.driver_id)] = (
                    ResourceAvailability(
                        resource_identifier=assignment.driver_id,
                        resource_kind=ResourceKind.HUMAN_RESOURCE,
                        available=True,
                        observed_state="assigned",
                    )
                )
            asset_identifier = assignment.plate or assignment.vehicle_id
            if asset_identifier:
                fleet.setdefault(
                    asset_identifier,
                    AssetReference(external_identifier=asset_identifier),
                )
                availability[(ResourceKind.ASSET, asset_identifier)] = (
                    ResourceAvailability(
                        resource_identifier=asset_identifier,
                        resource_kind=ResourceKind.ASSET,
                        available=True,
                        observed_state="assigned",
                    )
                )
            assignments.append(
                PlanningRuntimeAssignment(
                    task_identifier=assignment.route_id,
                    resource_identifier=assignment.driver_id,
                    asset_identifier=asset_identifier,
                    state=assignment.assignment_status.value,
                )
            )

        for resource in bundle.unused_drivers:
            resources.setdefault(
                resource.id,
                HumanResource(
                    external_identifier=resource.id,
                    display_name=resource.name,
                ),
            )
            availability.setdefault(
                (ResourceKind.HUMAN_RESOURCE, resource.id),
                ResourceAvailability(
                    resource_identifier=resource.id,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="unused",
                ),
            )

        for asset in bundle.available_vehicles:
            fleet.setdefault(
                asset.plate,
                AssetReference(external_identifier=asset.plate),
            )
            availability.setdefault(
                (ResourceKind.ASSET, asset.plate),
                ResourceAvailability(
                    resource_identifier=asset.plate,
                    resource_kind=ResourceKind.ASSET,
                    available=True,
                    observed_state=asset.state,
                ),
            )

        return PlanningRuntimeProducerInput(
            scope=PlanningRuntimeScope(
                organization_id=organization_id,
                operational_unit_id=operational_unit_id,
                planning_date=publication.planning_date,
                timezone=timezone,
            ),
            publication=publication,
            planning_version=bundle.planning.version,
            output_version=PlanningRuntimeOutputVersion(
                sequence=bundle.planning.version,
            ),
            resources=tuple(resources.values()),
            fleet=tuple(fleet.values()),
            assignments=tuple(assignments),
            capabilities=capabilities,
            availability=tuple(availability.values()),
            input_fingerprint=input_fingerprint,
            configuration_version=configuration_version,
            rules_version=bundle.generation_metadata.rules_version,
            evaluation_at=evaluated_at,
        )

from app.domain.planning_runtime.formatter import PlanningRuntimeOutputFormatter
from app.domain.planning_runtime.models import (
    PlanningRuntimeOutput,
    PlanningRuntimeOutputMetadata,
    PlanningRuntimeProducerInput,
)


class PlanningRuntimeProducer:
    def __init__(
        self,
        formatter: PlanningRuntimeOutputFormatter | None = None,
    ) -> None:
        self._formatter = formatter or PlanningRuntimeOutputFormatter()

    def produce(
        self,
        source: PlanningRuntimeProducerInput,
    ) -> PlanningRuntimeOutput:
        resources = tuple(
            sorted(
                source.resources,
                key=lambda item: item.external_identifier,
            )
        )
        fleet = tuple(
            sorted(
                source.fleet,
                key=lambda item: item.external_identifier,
            )
        )
        assignments = tuple(
            sorted(
                source.assignments,
                key=lambda item: (
                    item.task_identifier,
                    item.resource_identifier or "",
                    item.asset_identifier or "",
                    item.state,
                ),
            )
        )
        capabilities = tuple(
            sorted(
                source.capabilities,
                key=lambda item: (
                    item.resource_kind.value,
                    item.resource_identifier,
                    item.capability,
                ),
            )
        )
        availability = tuple(
            sorted(
                source.availability,
                key=lambda item: (
                    item.resource_kind.value,
                    item.resource_identifier,
                    str(item.available),
                    item.observed_state or "",
                ),
            )
        )
        metadata = PlanningRuntimeOutputMetadata(
            publication_id=source.publication.publication_id,
            publication_fingerprint=source.publication.fingerprint,
            input_fingerprint=source.input_fingerprint,
            configuration_version=source.configuration_version,
            rules_version=source.rules_version,
            generated_at=source.evaluation_at,
        )
        provisional = PlanningRuntimeOutput(
            scope=source.scope,
            planning_version=source.planning_version,
            publication_version=source.publication.publication_version,
            version=source.output_version,
            resources=resources,
            fleet=fleet,
            assignments=assignments,
            capabilities=capabilities,
            availability=availability,
            fingerprint="0" * 64,
            metadata=metadata,
        )
        return provisional.model_copy(
            update={
                "fingerprint": self._formatter.fingerprint_output(provisional),
            }
        )

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class CoreConcept(str, Enum):
    TASK = "task"
    OPERATIONAL_UNIT = "operational_unit"
    TIME_WINDOW = "time_window"
    ASSET = "asset"
    HUMAN_RESOURCE = "human_resource"
    TASK_CANCELLATION_EVENT = "task_cancellation_event"
    ASSET_UNAVAILABLE_EVENT = "asset_unavailable_event"
    HUMAN_RESOURCE_UNAVAILABLE_EVENT = (
        "human_resource_unavailable_event"
    )
    RESOURCE_POOL = "resource_pool"
    OPERATION_STATE_TRANSITION = "operation_state_transition"
    METRIC_OBSERVATION = "metric_observation"


class AdapterMappingLifecycle(str, Enum):
    ACTIVE = "active"
    FUTURE = "future"


class AdapterConceptMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_term: str
    core_concept: CoreConcept
    compatibility_field: str | None = None
    lifecycle: AdapterMappingLifecycle = AdapterMappingLifecycle.ACTIVE


class AdapterEventMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_event: str
    aliases: list[str] = Field(default_factory=list)
    core_concept: CoreConcept
    compatibility_event: str | None = None
    lifecycle: AdapterMappingLifecycle = AdapterMappingLifecycle.ACTIVE


class TabularImportAdapter(Protocol):
    adapter_id: str
    contract_version: str

    def aliases_for(
        self,
        dataset_type: str,
        organization_id: str = "default",
    ) -> dict[str, list[str]]:
        ...

    def concept_mappings(self) -> list[AdapterConceptMapping]:
        ...

    def event_mappings(self) -> list[AdapterEventMapping]:
        ...

    def recognized_operational_units(
        self,
        organization_id: str = "default",
    ) -> set[str]:
        ...

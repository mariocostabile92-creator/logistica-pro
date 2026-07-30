from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _CoreModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Task(_CoreModel):
    external_identifier: str = Field(min_length=1)
    task_type: str | None = None


class OperationalUnit(_CoreModel):
    external_identifier: str = Field(min_length=1)
    name: str | None = None


class HumanResource(_CoreModel):
    external_identifier: str = Field(min_length=1)
    display_name: str | None = None
    capabilities: tuple[str, ...] = Field(default_factory=tuple)


class AssetReference(_CoreModel):
    external_identifier: str = Field(min_length=1)
    category: str | None = None


class TimeWindow(_CoreModel):
    external_identifier: str = Field(min_length=1)
    starts_at: str | None = None
    ends_at: str | None = None


class TaskCancellationEvent(_CoreModel):
    task: Task
    reason: str | None = None
    source_event_identifier: str | None = None


class ResourceKind(str, Enum):
    HUMAN_RESOURCE = "human_resource"
    ASSET = "asset"


class ResourceAvailability(_CoreModel):
    resource_identifier: str = Field(min_length=1)
    resource_kind: ResourceKind
    available: bool
    observed_state: str | None = None
    reason: str | None = None
    origin: str | None = None

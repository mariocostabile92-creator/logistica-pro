from pydantic import BaseModel, Field

from app.domain.operation_events import (
    EventSimulation,
    OperationEntityType,
    OperationEventType,
)


class PlanningEventRequest(BaseModel):
    event_type: OperationEventType
    entity_type: OperationEntityType
    entity_id: str
    reason: str
    payload: dict[str, object] = Field(default_factory=dict)
    actor: str = "local_operator"


class SimulateEventResponse(EventSimulation):
    pass


class ApplyEventResponse(BaseModel):
    planning: dict[str, object]
    event: dict[str, object]
    diff: dict[str, object]
    version: int

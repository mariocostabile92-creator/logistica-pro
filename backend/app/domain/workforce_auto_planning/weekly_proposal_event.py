from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    StrictInt,
    field_validator,
)


class WeeklyWorkforceProposalEvent(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    event_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    proposal_version: StrictInt = Field(gt=0)
    event_type: str = Field(min_length=1)
    actor_id: str | None = None
    reason: str | None = None
    payload: SerializeAsAny[BaseModel]
    created_at: datetime

    @field_validator("payload")
    @classmethod
    def _payload_must_be_immutable(cls, value: BaseModel) -> BaseModel:
        if not value.model_config.get("frozen", False):
            raise ValueError("payload must be an immutable structured model")
        value.model_dump(mode="json")
        return value

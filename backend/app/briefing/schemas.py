from pydantic import BaseModel, Field


class GenerateDailyBriefingRequest(BaseModel):
    planning_id: int | None = Field(default=None, ge=1)

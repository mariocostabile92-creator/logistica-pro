from pydantic import BaseModel, Field


class AttachmentUpdateRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)

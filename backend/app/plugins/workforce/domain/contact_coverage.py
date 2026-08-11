from pydantic import BaseModel, Field


class WorkforceContactCoverage(BaseModel):
    total_members: int = Field(ge=0)
    active_members: int = Field(ge=0)
    phone_valid: int = Field(ge=0)
    phone_invalid: int = Field(ge=0)
    phone_missing: int = Field(ge=0)
    email_valid: int = Field(ge=0)
    email_invalid: int = Field(ge=0)
    email_missing: int = Field(ge=0)
    both_valid: int = Field(ge=0)
    no_channel: int = Field(ge=0)
    active_planning_available: bool
    active_planning_id: int | None = None
    recipients_total: int | None = Field(default=None, ge=0)
    recipients_phone_ready: int | None = Field(default=None, ge=0)
    recipients_email_ready: int | None = Field(default=None, ge=0)
    recipients_both: int | None = Field(default=None, ge=0)
    recipients_no_channel: int | None = Field(default=None, ge=0)

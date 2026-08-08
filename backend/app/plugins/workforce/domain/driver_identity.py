from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class DriverIdentitySource(str, Enum):
    JOURNAL = "journal"
    PLANNING = "planning"


class DriverIdentityResolutionStatus(str, Enum):
    MATCH = "MATCH"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


class DriverIdentityResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DriverIdentityResolutionStatus
    matched: bool
    source: str
    driver_identifier: str | None = None
    workforce_member_id: int | None = None
    external_identifier: str | None = None
    display_name: str | None = None
    candidate_count: int = 0

    @model_validator(mode="after")
    def validate_resolution(self):
        identity = (
            self.workforce_member_id,
            self.external_identifier,
            self.display_name,
        )
        if self.status is DriverIdentityResolutionStatus.MATCH:
            if not self.matched or any(value is None for value in identity):
                raise ValueError("A MATCH requires one complete Workforce identity.")
            if self.candidate_count != 1:
                raise ValueError("A MATCH requires exactly one candidate.")
        elif self.matched or any(value is not None for value in identity):
            raise ValueError("Only MATCH can expose a Workforce identity.")
        return self

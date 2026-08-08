from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class DriverSuggestionStatus(str, Enum):
    MATCH = "MATCH"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"


class DriverSuggestionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    workforce_member_id: int
    external_identifier: str
    display_name: str
    source: str
    evidence: tuple[str, ...] = ()


class DriverSuggestionResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DriverSuggestionStatus
    matched: bool
    conflict: bool = False
    source: str | None = None
    workforce_member_id: int | None = None
    external_identifier: str | None = None
    display_name: str | None = None
    journal_driver: DriverSuggestionCandidate | None = None
    planning_driver: DriverSuggestionCandidate | None = None
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_resolution(self):
        identity = (
            self.workforce_member_id,
            self.external_identifier,
            self.display_name,
        )
        if self.status is DriverSuggestionStatus.MATCH:
            if not self.matched or self.conflict:
                raise ValueError("MATCH requires one non-conflicting driver.")
            if any(value is None for value in identity) or not self.source:
                raise ValueError("MATCH requires one complete driver identity.")
        elif self.matched or any(value is not None for value in identity):
            raise ValueError("Only MATCH can expose the selected identity.")
        if self.status is DriverSuggestionStatus.CONFLICT:
            if not self.conflict or not self.journal_driver or not self.planning_driver:
                raise ValueError("CONFLICT requires Journal and Planning drivers.")
        elif self.conflict:
            raise ValueError("Only CONFLICT can set conflict=true.")
        return self

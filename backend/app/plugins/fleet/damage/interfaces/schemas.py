from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.plugins.fleet.damage.domain.damage_policy import DamageCountingPeriod


def required(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Il valore non può essere vuoto.")
    return text


class DamageCreateRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    source_movement_id: str | None = None
    declared_driver: str | None = None
    occurred_at: datetime
    origin: str
    manual_reason: str | None = None
    description: str = Field(min_length=1, max_length=4000)
    severity: str = "media"
    vehicle_operational_status: str = "disponibile"
    repair_shop: str | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    final_cost: Decimal | None = Field(default=None, ge=0)
    actor: str = "fleet_manager"
    workforce_member_id: int | None = Field(default=None, gt=0)
    attribution_source: Literal["journal", "planning"] | None = None

    _description = field_validator("description")(required)
    _actor = field_validator("actor")(required)

    @model_validator(mode="after")
    def complete_driver_attribution(self):
        if (self.workforce_member_id is None) != (self.attribution_source is None):
            raise ValueError(
                "Driver e fonte attribuzione devono essere confermati insieme."
            )
        return self


class DamageDriverAttributionResponse(BaseModel):
    workforce_member_id: int
    external_identifier_snapshot: str
    name_snapshot: str
    source: str
    attributed_at: str
    attributed_by: str
    reason: str | None = None


class DamageDriverSuggestionCandidateResponse(BaseModel):
    workforce_member_id: int
    external_identifier: str
    display_name: str


class DamageDriverSuggestionResponse(BaseModel):
    status: Literal["MATCH", "NOT_FOUND", "AMBIGUOUS", "CONFLICT"]
    conflict: bool = False
    driver: DamageDriverSuggestionCandidateResponse | None = None
    source: Literal["journal", "planning"] | None = None
    evidence: list[str] = Field(default_factory=list)
    journal_driver: DamageDriverSuggestionCandidateResponse | None = None
    planning_driver: DamageDriverSuggestionCandidateResponse | None = None


class DamagePolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    free_events_count: int = Field(ge=0)
    counting_period: DamageCountingPeriod


class DamagePolicyResponse(BaseModel):
    enabled: bool
    free_events_count: int
    counting_period: DamageCountingPeriod
    updated_at: str | None = None


class DamageDriverPolicyStateResponse(BaseModel):
    policy_enabled: bool
    total_attributed_cases: int
    countable_cases: int
    free_events_count: int
    free_events_used: int
    events_over_threshold: int
    next_event_is_over_threshold: bool
    counting_period: DamageCountingPeriod
    period_start: str | None = None
    period_end: str | None = None


class DamageUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=4000)
    severity: str | None = None
    vehicle_operational_status: str | None = None
    operational_reason: str | None = Field(default=None, max_length=2000)
    repair_shop: str | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    final_cost: Decimal | None = Field(default=None, ge=0)
    actor: str = "fleet_manager"


class DamageStatusRequest(BaseModel):
    status: str
    note: str = Field(min_length=1, max_length=2000)
    restoration_status: str | None = None
    actor: str = "fleet_manager"


class DamageNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    actor: str = "fleet_manager"


class ManualOperationalStatusRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=2000)
    origin: str
    actor: str = "fleet_manager"
    override_restriction: bool = False

    _reason = field_validator("reason")(required)
    _actor = field_validator("actor")(required)

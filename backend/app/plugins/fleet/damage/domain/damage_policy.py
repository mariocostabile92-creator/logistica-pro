from datetime import date
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


class DamageCountingPeriod(str, Enum):
    ALL_TIME = "all_time"
    CALENDAR_YEAR = "calendar_year"
    ROLLING_12_MONTHS = "rolling_12_months"


class DamagePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: str = Field(min_length=1)
    enabled: bool = False
    free_events_count: int = Field(default=0, ge=0)
    counting_period: DamageCountingPeriod = DamageCountingPeriod.ALL_TIME
    created_at: str | None = None
    updated_at: str | None = None


class DamageDriverPolicyState(BaseModel):
    model_config = ConfigDict(frozen=True)

    workforce_member_id: int = Field(gt=0)
    policy_enabled: bool
    total_attributed_cases: int = Field(ge=0)
    countable_cases: int = Field(ge=0)
    free_events_count: int = Field(ge=0)
    free_events_used: int = Field(ge=0)
    events_over_threshold: int = Field(ge=0)
    next_event_is_over_threshold: bool
    counting_period: DamageCountingPeriod
    period_start: date | None = None
    period_end: date | None = None


COUNTABLE_DAMAGE_STATUSES = frozenset({
    "nuova",
    "in_valutazione",
    "preventivo_richiesto",
    "preventivo_ricevuto",
    "riparazione_programmata",
    "in_riparazione",
    "chiusa",
})


def is_damage_countable(damage_case: Mapping[str, object]) -> bool:
    """A valid attributed case counts unless its real status is annulled."""
    member_id = damage_case.get("driver_workforce_member_id")
    try:
        has_driver = int(member_id) > 0 if member_id is not None else False
    except (TypeError, ValueError):
        has_driver = False
    return has_driver and str(damage_case.get("status")) in COUNTABLE_DAMAGE_STATUSES


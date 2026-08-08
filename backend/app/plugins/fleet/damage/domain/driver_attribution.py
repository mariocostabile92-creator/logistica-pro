from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DamageDriverAttributionSource(str, Enum):
    JOURNAL = "journal"
    PLANNING = "planning"
    MANUAL = "manual"


class CanonicalDamageDriverAttribution(BaseModel):
    """Canonical Workforce reference to persist on a damage case."""

    model_config = ConfigDict(frozen=True)

    workforce_member_id: int = Field(gt=0)
    source: DamageDriverAttributionSource
    attributed_by: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("attributed_by")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        return value.strip()

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class DamageDriverAttributionRejected(ValueError):
    """Raised when the canonical Workforce identity is outside the case tenant."""


from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


COVERAGE_TYPES = {
    "rca", "kasko", "furto_incendio", "cristalli",
    "eventi_atmosferici", "assistenza", "altro",
}
POLICY_STATUSES = {"attiva", "in_scadenza", "scaduta", "sospesa"}


class InsurancePolicyRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    company: str = Field(min_length=1, max_length=240)
    policy_number: str = Field(min_length=1, max_length=200)
    coverage_type: str
    starts_on: date
    expires_on: date
    coverage_limit: Decimal | None = Field(default=None, ge=0)
    insurance_deductible: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)
    status: str = "attiva"
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)

    @field_validator("coverage_type")
    @classmethod
    def valid_coverage(cls, value: str) -> str:
        if value not in COVERAGE_TYPES:
            raise ValueError("Tipo di copertura non supportato.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in POLICY_STATUSES:
            raise ValueError("Stato polizza non supportato.")
        return value


class InsurancePolicyUpdateRequest(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=240)
    policy_number: str | None = Field(default=None, min_length=1, max_length=200)
    coverage_type: str | None = None
    starts_on: date | None = None
    expires_on: date | None = None
    coverage_limit: Decimal | None = Field(default=None, ge=0)
    insurance_deductible: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)

    @field_validator("coverage_type")
    @classmethod
    def valid_coverage(cls, value: str | None) -> str | None:
        if value is not None and value not in COVERAGE_TYPES:
            raise ValueError("Tipo di copertura non supportato.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in POLICY_STATUSES:
            raise ValueError("Stato polizza non supportato.")
        return value

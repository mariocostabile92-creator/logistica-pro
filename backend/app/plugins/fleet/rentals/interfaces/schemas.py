from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


STATUSES = {"programmato", "attivo", "prorogato", "concluso", "annullato"}
REASONS = {"manutenzione", "danno", "fermo_tecnico", "picco_operativo", "altro"}


class RentalCreateRequest(BaseModel):
    vehicle_id: int | None = Field(default=None, gt=0)
    damage_case_id: int | None = Field(default=None, gt=0)
    maintenance_id: int | None = Field(default=None, gt=0)
    replacement_vehicle: str = Field(min_length=1, max_length=240)
    rental_company: str = Field(min_length=1, max_length=240)
    contract_number: str | None = Field(default=None, max_length=200)
    start_date: date
    expected_end_date: date
    end_date: date | None = None
    reason: str
    status: str = "programmato"
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        if value not in REASONS:
            raise ValueError("Motivazione noleggio non supportata.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("Stato noleggio non supportato.")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if self.expected_end_date < self.start_date:
            raise ValueError("La fine prevista non può precedere l'inizio.")
        return self


class RentalUpdateRequest(BaseModel):
    replacement_vehicle: str | None = Field(default=None, min_length=1, max_length=240)
    rental_company: str | None = Field(default=None, min_length=1, max_length=240)
    contract_number: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    expected_end_date: date | None = None
    end_date: date | None = None
    reason: str | None = None
    status: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in REASONS:
            raise ValueError("Motivazione noleggio non supportata.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in STATUSES:
            raise ValueError("Stato noleggio non supportato.")
        return value

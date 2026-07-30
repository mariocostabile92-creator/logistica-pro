from pydantic import BaseModel, Field, field_validator


STATUSES = {
    "da_valutare", "in_verifica", "applicata", "non_applicabile", "chiusa",
}


class FranchiseCreateRequest(BaseModel):
    damage_case_id: int = Field(gt=0)
    motivation: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)


class FranchiseUpdateRequest(BaseModel):
    status: str | None = None
    motivation: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = Field(default="fleet_manager", min_length=1, max_length=120)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in STATUSES:
            raise ValueError("Stato franchigia non supportato.")
        return value

from datetime import date

from pydantic import BaseModel, Field, model_validator


class PlanningDraftCreateRequest(BaseModel):
    organization_id: str = Field(default="default", min_length=1, max_length=120)
    operational_unit_id: str = Field(default="default", min_length=1, max_length=120)
    operational_unit_name: str | None = Field(default=None, max_length=120)
    planning_date: date
    name: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class PlanningDraftMetadataUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_a_change(self):
        if not ({"name", "note"} & self.model_fields_set):
            raise ValueError("Almeno un metadato deve essere specificato.")
        return self


class PlanningDraftVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class PlanningDraftRestoreRequest(PlanningDraftVersionRequest):
    target_version: int = Field(ge=1)

from datetime import datetime

from pydantic import BaseModel, Field, JsonValue, field_validator

from app.core.configuration.models import (
    ConfigurationScope,
    ConfigurationValidationResult,
    ConfigurationVersion,
)


KEY_PATTERN = r"^[a-z0-9][a-z0-9_.-]*$"


class ConfigurationValueInput(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=KEY_PATTERN)
    value: JsonValue


class ConfigurationSectionInput(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=KEY_PATTERN)
    values: list[ConfigurationValueInput] = Field(
        default_factory=list,
        max_length=500,
    )


class ConfigurationValidationRequest(BaseModel):
    organization_id: str = Field(default="default", min_length=1, max_length=120)
    operational_unit_id: str | None = Field(default=None, max_length=120)
    adapter_id: str | None = Field(default=None, max_length=120)
    sections: list[ConfigurationSectionInput] = Field(
        default_factory=list,
        max_length=100,
    )


class ConfigurationVersionCreateRequest(ConfigurationValidationRequest):
    created_by: str = Field(
        default="local_operator",
        min_length=1,
        max_length=120,
    )
    note: str | None = Field(default=None, max_length=1000)
    valid_from: str | None = None

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, value: str | None) -> str | None:
        if value is None:
            return None
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class ConfigurationVersionsResponse(BaseModel):
    contract_version: str = "1.0"
    scope: ConfigurationScope
    items: list[ConfigurationVersion]


class ConfigurationValidationResponse(ConfigurationValidationResult):
    contract_version: str = "1.0"

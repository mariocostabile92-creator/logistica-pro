from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


class ConfigurationValueSource(str, Enum):
    PLATFORM_DEFAULT = "platform_default"
    ORGANIZATION = "organization"
    OPERATIONAL_UNIT = "operational_unit"
    FUTURE_ADAPTER = "future_adapter"


class ConfigurationScope(BaseModel):
    organization_id: str = "default"
    operational_unit_id: str | None = None
    adapter_id: str | None = None

    @field_validator(
        "organization_id",
        "operational_unit_id",
        "adapter_id",
    )
    @classmethod
    def normalize_scope_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def require_organization(self):
        if not self.organization_id:
            raise ValueError("organization_id è obbligatorio.")
        return self


class ConfigurationValue(BaseModel):
    key: str
    value: JsonValue
    source: ConfigurationValueSource

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        text = value.strip().casefold()
        if not text or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_.-"
            for character in text
        ):
            raise ValueError("Chiave configurazione non valida.")
        return text


class ConfigurationSection(BaseModel):
    key: str
    values: list[ConfigurationValue] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return ConfigurationValue.normalize_key(value)

    @model_validator(mode="after")
    def unique_value_keys(self):
        keys = [item.key for item in self.values]
        if len(keys) != len(set(keys)):
            raise ValueError(
                f"Valori duplicati nella sezione {self.key}."
            )
        return self


class ConfigurationVersion(BaseModel):
    number: int = Field(ge=0)
    created_at: str
    valid_from: str
    created_by: str
    note: str | None = None


class AppliedConfigurationVersion(BaseModel):
    scope: ConfigurationScope
    number: int = Field(ge=1)


class ConfigurationMetadata(BaseModel):
    requested_scope: ConfigurationScope
    resolved_scope: ConfigurationScope | None = None
    fallback_used: bool
    fallback_sections: list[str] = Field(default_factory=list)
    applied_versions: list[AppliedConfigurationVersion] = Field(
        default_factory=list
    )
    validation_status: str = "valid"
    warnings: list[str] = Field(default_factory=list)
    contract_version: str = "1.0"


class Configuration(BaseModel):
    configuration_id: str
    version: ConfigurationVersion
    metadata: ConfigurationMetadata
    sections: list[ConfigurationSection]


class ConfigurationRevision(BaseModel):
    scope: ConfigurationScope
    version: ConfigurationVersion
    sections: list[ConfigurationSection]


class ConfigurationValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fallback_sections: list[str] = Field(default_factory=list)

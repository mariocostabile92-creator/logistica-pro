import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.plugins.fleet.domain.models import Asset, AssetEvent


TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _required_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Il valore non può essere vuoto.")
    return text


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _token(value: str) -> str:
    text = _required_text(value).casefold()
    if not TOKEN_PATTERN.fullmatch(text):
        raise ValueError(
            "Usa lettere minuscole, numeri, punto, trattino o underscore."
        )
    return text


def _capability_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        capability = _token(value)
        if capability not in normalized:
            normalized.append(capability)
    return normalized


def _iso_date(value: str | None) -> str | None:
    text = _optional_text(value)
    if text:
        date.fromisoformat(text)
    return text


class AssetCreateRequest(BaseModel):
    external_identifier: str = Field(min_length=1, max_length=120)
    plate: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=80)
    status: str = Field(default="active", max_length=64)
    availability: str = Field(default="available", max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    actor: str = Field(default="local_operator", max_length=120)

    _validate_external_identifier = field_validator(
        "external_identifier"
    )(_required_text)
    _validate_plate = field_validator("plate")(_optional_text)
    _validate_category = field_validator("category")(_optional_text)
    _validate_notes = field_validator("notes")(_optional_text)
    _validate_status = field_validator("status")(_token)
    _validate_availability = field_validator("availability")(_token)
    _validate_capabilities = field_validator("capabilities")(_capability_list)
    _validate_actor = field_validator("actor")(_required_text)

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class AssetUpdateRequest(BaseModel):
    plate: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] | None = Field(default=None, max_length=100)
    actor: str = Field(default="local_operator", max_length=120)

    _validate_plate = field_validator("plate")(_optional_text)
    _validate_category = field_validator("category")(_optional_text)
    _validate_notes = field_validator("notes")(_optional_text)
    _validate_actor = field_validator("actor")(_required_text)

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        return _token(value) if value is not None else None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        return _capability_list(value) if value is not None else None


class AvailabilityObservationRequest(BaseModel):
    availability: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    actor: str = Field(default="local_operator", max_length=120)

    _validate_availability = field_validator("availability")(_token)
    _validate_note = field_validator("note")(_optional_text)
    _validate_actor = field_validator("actor")(_required_text)


class AssetDocumentCreateRequest(BaseModel):
    document_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    reference: str | None = Field(default=None, max_length=160)
    issued_on: str | None = Field(default=None, max_length=10)
    expires_on: str | None = Field(default=None, max_length=10)
    notes: str | None = Field(default=None, max_length=1000)
    actor: str = Field(default="local_operator", max_length=120)

    _validate_document_type = field_validator("document_type")(_token)
    _validate_name = field_validator("name")(_required_text)
    _validate_reference = field_validator("reference")(_optional_text)
    _validate_issued_on = field_validator("issued_on")(_iso_date)
    _validate_expires_on = field_validator("expires_on")(_iso_date)
    _validate_notes = field_validator("notes")(_optional_text)
    _validate_actor = field_validator("actor")(_required_text)


class AssetListResponse(BaseModel):
    contract_version: str = "1.0"
    items: list[Asset]


class AssetEventsResponse(BaseModel):
    contract_version: str = "1.0"
    items: list[AssetEvent]

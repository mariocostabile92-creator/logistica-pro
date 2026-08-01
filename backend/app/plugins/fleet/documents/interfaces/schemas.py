from datetime import date

from pydantic import BaseModel, Field, field_validator
from app.plugins.fleet.documents.domain.status_evaluator import DOCUMENT_STATUSES


DOCUMENT_TYPES = {
    "carta_circolazione", "assicurazione", "revisione", "bollo",
    "contratto_noleggio", "contratto_leasing", "manuale",
    "manutenzione", "autorizzazione", "certificazione", "altro",
}


class VehicleDocumentRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    document_type: str
    title: str = Field(min_length=1, max_length=240)
    document_number: str | None = Field(default=None, max_length=200)
    issuer: str | None = Field(default=None, max_length=240)
    issued_at: date | None = None
    expires_at: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    file_name: str | None = Field(default=None, max_length=255)
    file_reference: str | None = Field(default=None, max_length=1000)

    @field_validator("document_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        if value not in DOCUMENT_TYPES:
            raise ValueError("Tipologia documento non supportata.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in DOCUMENT_STATUSES | {"valido", "mancante"}:
            raise ValueError("Stato documento non supportato.")
        return value


class VehicleDocumentUpdateRequest(BaseModel):
    document_type: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    document_number: str | None = Field(default=None, max_length=200)
    issuer: str | None = Field(default=None, max_length=240)
    issued_at: date | None = None
    expires_at: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    file_name: str | None = Field(default=None, max_length=255)
    file_reference: str | None = Field(default=None, max_length=1000)

    @field_validator("document_type")
    @classmethod
    def valid_type(cls, value: str | None) -> str | None:
        if value is not None and value not in DOCUMENT_TYPES:
            raise ValueError("Tipologia documento non supportata.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in DOCUMENT_STATUSES | {"valido", "mancante"}:
            raise ValueError("Stato documento non supportato.")
        return value

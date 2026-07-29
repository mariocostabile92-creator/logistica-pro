from enum import Enum

from pydantic import BaseModel, Field


class AssetEventType(str, Enum):
    ASSET_CREATED = "AssetCreated"
    ASSET_UPDATED = "AssetUpdated"
    ASSET_AVAILABLE = "AssetAvailable"
    ASSET_UNAVAILABLE = "AssetUnavailable"
    ASSET_MAINTENANCE_STARTED = "AssetMaintenanceStarted"
    ASSET_MAINTENANCE_ENDED = "AssetMaintenanceEnded"
    ASSET_AVAILABILITY_CHANGED = "AssetAvailabilityChanged"
    ASSET_AVAILABILITY_OBSERVED = "AssetAvailabilityObserved"
    ASSET_DOCUMENT_ADDED = "AssetDocumentAdded"
    ASSET_RESERVE_ASSIGNED = "AssetReserveAssigned"
    ASSET_DOCUMENT_OBSERVED = "AssetDocumentObserved"
    ASSET_ASSOCIATION_CHANGED = "AssetAssociationChanged"
    OPERATIONAL_STATUS_CHANGED = "stato_operativo_mezzo_modificato"


class AssetDocument(BaseModel):
    id: int
    asset_id: int
    document_type: str
    name: str
    reference: str | None = None
    issued_on: str | None = None
    expires_on: str | None = None
    notes: str | None = None
    created_at: str


class Asset(BaseModel):
    id: int
    external_identifier: str
    plate: str | None = None
    category: str | None = None
    status: str
    availability: str
    notes: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    documents: list[AssetDocument] = Field(default_factory=list)
    created_at: str
    updated_at: str


class AssetEvent(BaseModel):
    id: int
    asset_id: int
    event_type: AssetEventType
    occurred_at: str
    actor: str
    details: dict[str, object] = Field(default_factory=dict)
    contract_version: str = "1.0"


def availability_event_type(
    previous: str,
    current: str,
) -> AssetEventType:
    previous_key = previous.strip().casefold()
    current_key = current.strip().casefold()
    if previous_key == current_key:
        return AssetEventType.ASSET_AVAILABILITY_OBSERVED
    if previous_key == "maintenance" and current_key != "maintenance":
        return AssetEventType.ASSET_MAINTENANCE_ENDED
    if current_key == "maintenance":
        return AssetEventType.ASSET_MAINTENANCE_STARTED
    if current_key == "available":
        return AssetEventType.ASSET_AVAILABLE
    if current_key == "unavailable":
        return AssetEventType.ASSET_UNAVAILABLE
    return AssetEventType.ASSET_AVAILABILITY_CHANGED

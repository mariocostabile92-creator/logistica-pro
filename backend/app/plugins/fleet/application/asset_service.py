from app.plugins.fleet.domain.models import (
    Asset,
    AssetDocument,
    AssetEvent,
    availability_event_type,
)
from app.plugins.fleet.infrastructure import repository


class AssetNotFoundError(LookupError):
    pass


class AssetValidationError(ValueError):
    pass


def list_assets() -> list[Asset]:
    return repository.list_assets()


def get_asset(asset_id: int) -> Asset:
    asset = repository.get_asset(asset_id)
    if not asset:
        raise AssetNotFoundError("Asset non trovato.")
    return asset


def create_asset(
    values: dict[str, object],
    actor: str,
) -> Asset:
    return repository.create_asset(values, actor=actor)


def update_asset(
    asset_id: int,
    changes: dict[str, object],
    actor: str,
) -> Asset:
    if not changes:
        raise AssetValidationError("Nessuna modifica specificata.")
    if any(
        field in changes and changes[field] is None
        for field in ("status", "capabilities")
    ):
        raise AssetValidationError(
            "Status e capability non accettano il valore null."
        )
    asset = repository.update_asset(asset_id, changes, actor=actor)
    if not asset:
        raise AssetNotFoundError("Asset non trovato.")
    return asset


def observe_availability(
    asset_id: int,
    availability: str,
    note: str | None,
    actor: str,
) -> Asset:
    current = get_asset(asset_id)
    event_type = availability_event_type(
        current.availability,
        availability,
    )
    asset = repository.observe_availability(
        asset_id=asset_id,
        availability=availability,
        note=note,
        actor=actor,
        event_type=event_type,
    )
    if not asset:
        raise AssetNotFoundError("Asset non trovato.")
    return asset


def add_document(
    asset_id: int,
    values: dict[str, object],
    actor: str,
) -> AssetDocument:
    get_asset(asset_id)
    document = repository.add_document(
        asset_id=asset_id,
        values=values,
        actor=actor,
    )
    if not document:
        raise AssetNotFoundError("Asset non trovato.")
    return document


def list_events(asset_id: int) -> list[AssetEvent]:
    get_asset(asset_id)
    return repository.list_events(asset_id)

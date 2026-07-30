from datetime import date, timedelta

from app.domain.core_language.models import ResourceAvailability, ResourceKind
from app.plugins.fleet.application.asset_service import list_assets
from app.plugins.fleet.domain.errors import FleetSyncConfirmationError
from app.plugins.fleet.domain.sync_models import FleetBriefingSnapshot
from app.plugins.fleet.importer.registry_interpreter import build_registry_preview
from app.plugins.fleet.infrastructure import sync_repository


def preview_sync(
    *,
    content: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
):
    return build_registry_preview(
        content=content,
        filename=filename,
        assets=list_assets(),
        metadata_by_asset=sync_repository.metadata_by_asset(),
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )


def confirm_sync(
    *,
    content: bytes,
    filename: str,
    confirmed_fingerprint: str,
    selected_rows: list[int],
    actor: str,
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
):
    preview = preview_sync(
        content=content,
        filename=filename,
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )
    if preview.fingerprint != confirmed_fingerprint:
        raise FleetSyncConfirmationError(
            "Il file e cambiato dopo la preview. Analizzalo nuovamente."
        )
    return sync_repository.apply_sync(preview, selected_rows, actor)


def core_availability() -> list[ResourceAvailability]:
    return [
        ResourceAvailability(
            resource_identifier=asset.external_identifier,
            resource_kind=ResourceKind.ASSET,
            available=asset.availability in {
                "available",
                "reserve",
                "disponibile",
                "disponibile_con_limitazioni",
            },
            observed_state=asset.availability,
            reason=asset.operational_status_reason,
            origin=asset.operational_status_origin,
        )
        for asset in list_assets()
    ]


def briefing_snapshot(operation_date: str | None = None) -> FleetBriefingSnapshot:
    assets = list_assets()
    reference_date = date.fromisoformat(operation_date) if operation_date else date.today()
    attention_limit = reference_date + timedelta(days=30)
    documents_attention = 0
    for asset in assets:
        for document in asset.documents:
            if not document.expires_on:
                continue
            expiry = date.fromisoformat(document.expires_on)
            documents_attention += expiry <= attention_limit
    latest = sync_repository.latest_sync()
    summary = latest.get("summary", {}) if latest else {}
    return FleetBriefingSnapshot(
        total_assets=len(assets),
        unavailable_assets=sum(asset.availability == "unavailable" for asset in assets),
        maintenance_assets=sum(asset.availability == "maintenance" for asset in assets),
        reserve_assets=sum(asset.availability == "reserve" for asset in assets),
        documents_attention=documents_attention,
        recent_updates=int(summary.get("created_assets", 0)) + int(summary.get("updated_assets", 0)),
        unresolved_conflicts=int(summary.get("unresolved_conflicts", 0)),
    )


def latest_sync():
    return sync_repository.latest_sync()

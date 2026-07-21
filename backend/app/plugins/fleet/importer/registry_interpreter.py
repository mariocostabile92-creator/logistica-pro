from datetime import date, datetime
from hashlib import sha256
import re
from typing import Any

from app.importers.workbook_profiler.errors import WorkbookImportBlockedError
from app.importers.workbook_profiler.preview_builder import build_workbook_profile
from app.plugins.fleet.application.registry_configuration import (
    fleet_registry_configuration,
)
from app.plugins.fleet.domain.models import Asset
from app.plugins.fleet.domain.sync_models import (
    FleetInterpretationStatus,
    FleetSyncAction,
    FleetSyncItem,
    FleetSyncPreview,
    FleetSyncSummary,
    SensitiveField,
)
from app.plugins.fleet.importer.registry_aliases import registry_aliases
from app.utils.text_normalizer import normalize_plate, normalize_text


def _strict_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _full_card_or_pin(value: Any) -> bool:
    text = str(value or "")
    digits = re.sub(r"\D", "", text)
    return bool(re.search(r"\bpin\b", text, re.IGNORECASE) or len(digits) >= 8)


def _sensitive_columns(columns: list[str]) -> set[str]:
    configured = fleet_registry_configuration().get("sensitive_aliases", [])
    aliases = {normalize_text(item) for item in configured if str(item).strip()}
    result = set()
    for column in columns:
        normalized = normalize_text(column)
        if any(alias and (alias == normalized or alias in normalized) for alias in aliases):
            result.add(column)
    return result


def _availability(
    status: Any,
    availability: Any,
    workshop: Any,
    damage: Any,
) -> tuple[str, FleetInterpretationStatus]:
    configuration = fleet_registry_configuration()
    explicit = normalize_text(
        " ".join(str(value or "") for value in (status, availability))
    )
    configured = configuration.get("availability_mappings", {})
    if isinstance(configured, dict):
        ordered_states = sorted(
            configured,
            key=lambda state: (
                state == "available",
                -max(
                    (len(normalize_text(alias)) for alias in configured.get(state, [])),
                    default=0,
                ),
            ),
        )
        for state in ordered_states:
            aliases = configured[state]
            if isinstance(aliases, list) and any(
                normalize_text(alias)
                and f" {normalize_text(alias)} " in f" {explicit} "
                for alias in aliases
            ):
                return str(state), FleetInterpretationStatus.INFERRED

    if explicit:
        return "unknown", FleetInterpretationStatus.NEEDS_CONFIRMATION

    negative_values = {
        normalize_text(item)
        for item in configuration.get("negative_issue_values", [])
        if str(item).strip()
    }
    workshop_value = normalize_text(workshop)
    damage_value = normalize_text(damage)
    workshop_issue = bool(workshop_value and workshop_value not in negative_values)
    damage_issue = bool(damage_value and damage_value not in negative_values)
    if (
        workshop_issue
        and configuration.get("workshop_presence_means_maintenance") is True
    ):
        return "maintenance", FleetInterpretationStatus.INFERRED
    if (
        damage_issue
        and configuration.get("damage_presence_means_unavailable") is True
    ):
        return "unavailable", FleetInterpretationStatus.INFERRED
    if configuration.get("infer_available_when_no_issue") is True:
        return "available", FleetInterpretationStatus.INFERRED
    return "unknown", FleetInterpretationStatus.NEEDS_CONFIRMATION


def _asset_current(asset: Asset) -> dict[str, object]:
    return {
        "asset_id": asset.id,
        "external_identifier": asset.external_identifier,
        "plate": asset.plate,
        "category": asset.category,
        "status": asset.status,
        "availability": asset.availability,
        "capabilities": asset.capabilities,
    }


def _difference(current: dict[str, object], proposed: dict[str, object]) -> dict[str, dict[str, object]]:
    fields = ("plate", "category", "status", "availability")
    return {
        field: {"before": current.get(field), "after": proposed.get(field)}
        for field in fields
        if proposed.get(field) is not None and current.get(field) != proposed.get(field)
    }


def build_registry_preview(
    *,
    content: bytes,
    filename: str,
    assets: list[Asset],
    metadata_by_asset: dict[int, dict[str, object]],
    sheet_name: str | None = None,
    header_row: int | None = None,
    manual_mapping: dict[str, str | None] | None = None,
) -> FleetSyncPreview:
    profile = build_workbook_profile(
        content=content,
        filename=filename,
        dataset_type="fleet",
        aliases=registry_aliases(),
        sheet_name=sheet_name,
        header_row=header_row,
        manual_mapping=manual_mapping,
    )
    if not profile.import_allowed:
        raise WorkbookImportBlockedError(profile.blocking_reasons)
    fields = {
        item.source_column: item.target_field
        for item in profile.mapping
        if item.target_field and item.status == "recognized"
    }
    sensitive_columns = _sensitive_columns(profile.columns)
    by_external = {asset.external_identifier.casefold(): asset for asset in assets}
    by_plate = {normalize_plate(asset.plate): asset for asset in assets if asset.plate}
    assets_by_id = {asset.id: asset for asset in assets}
    by_alternative = {
        str(identifier).casefold(): assets_by_id[asset_id]
        for asset_id, metadata in metadata_by_asset.items()
        if asset_id in assets_by_id
        for identifier in metadata.get("alternative_identifiers", [])
        if str(identifier).strip()
    }
    seen_plates: set[str] = set()
    items: list[FleetSyncItem] = []

    for offset, row in enumerate(profile.table_rows):
        values: dict[str, Any] = {}
        row_sensitive = set(sensitive_columns)
        for column, value in row.items():
            field = fields.get(column)
            if column in sensitive_columns:
                continue
            if field == "fuel_card" and _full_card_or_pin(value):
                row_sensitive.add(column)
                continue
            if field:
                values[field] = value

        plate = normalize_plate(values.get("vehicle_plate")) or None
        external = str(values.get("external_identifier") or "").strip() or plate
        current_by_external = by_external.get(external.casefold()) if external else None
        current_by_plate = by_plate.get(plate) if plate else None
        current_by_alternative = by_alternative.get(external.casefold()) if external else None
        identity_matches = {
            asset.id: asset
            for asset in (
                current_by_external,
                current_by_plate,
                current_by_alternative,
            )
            if asset is not None
        }
        current_asset = next(iter(identity_matches.values()), None)
        sensitive_fields = [SensitiveField(column=name) for name in sorted(row_sensitive)]
        availability, interpretation = _availability(
            values.get("status"), values.get("availability"),
            values.get("workshop"), values.get("damage"),
        )
        proposed = {
            "external_identifier": external,
            "plate": plate,
            "category": str(values.get("category") or values.get("vehicle_model") or "").strip() or None,
            "status": "active",
            "availability": availability,
            "vehicle_model": str(values.get("vehicle_model") or "").strip() or None,
            "rental_company": str(values.get("rental_company") or "").strip() or None,
            "observed_assigned_human_resource": str(values.get("driver_name") or "").strip() or None,
            "observed_second_human_resource": str(values.get("second_driver_name") or "").strip() or None,
            "replacement_asset_reference": normalize_plate(values.get("replacement_vehicle")) or None,
            "parking_location": str(values.get("parking") or "").strip() or None,
            "document_type": str(values.get("document") or "").strip() or None,
            "document_expiry": _strict_date(values.get("expirations")),
            "source_reference": f"{profile.selected_sheet.name}:row:{profile.row_numbers[offset]}",
        }
        current = _asset_current(current_asset) if current_asset else None
        difference = _difference(current or {}, proposed)

        if not external or not plate or len(plate) < 5:
            action = FleetSyncAction.INVALID_ROW
            reason = "Identificativo Asset o targa valida assente."
            selected = False
            confidence = 0.2
        elif plate in seen_plates:
            action = FleetSyncAction.POSSIBLE_DUPLICATE
            reason = "La stessa targa compare piu volte nel workbook."
            selected = False
            confidence = 0.45
        elif len(identity_matches) > 1:
            action = FleetSyncAction.CONFLICT
            reason = "Gli identificativi esatti puntano a Asset differenti."
            selected = False
            confidence = 0.3
        elif (
            (current_by_external or current_by_alternative)
            and current_asset
            and current_asset.plate
            and plate != normalize_plate(current_asset.plate)
        ):
            action = FleetSyncAction.CONFLICT
            reason = "La targa proposta contrasta con l'identificativo esterno esistente."
            selected = False
            confidence = 0.4
        elif current_asset is None:
            action = FleetSyncAction.NEW_ASSET
            reason = "Nessun Asset esistente con identificativo o targa esatti."
            selected = interpretation != FleetInterpretationStatus.NEEDS_CONFIRMATION
            confidence = 0.95 if selected else 0.72
        else:
            metadata = metadata_by_asset.get(current_asset.id, {})
            alternative_difference = bool(
                external
                and external.casefold()
                != current_asset.external_identifier.casefold()
                and external.casefold()
                not in {
                    str(item).casefold()
                    for item in metadata.get("alternative_identifiers", [])
                }
            )
            metadata_difference = any(
                proposed.get(field) and proposed.get(field) != metadata.get(field)
                for field in (
                    "vehicle_model", "rental_company", "observed_assigned_human_resource",
                    "observed_second_human_resource", "replacement_asset_reference", "parking_location",
                )
            ) or alternative_difference
            supporting_match = any(
                proposed.get(field)
                and proposed.get(field) == metadata.get(field)
                for field in ("vehicle_model", "rental_company")
            )
            document_difference = bool(
                proposed.get("document_expiry")
                and not any(
                    document.document_type
                    == str(proposed.get("document_type") or "observed_expiration")
                    and document.expires_on == proposed.get("document_expiry")
                    for document in current_asset.documents
                )
            )
            if difference or metadata_difference or document_difference:
                action = FleetSyncAction.UPDATE_EXISTING
                reason = "Rilevate differenze rispetto all'Asset Registry."
                selected = interpretation != FleetInterpretationStatus.NEEDS_CONFIRMATION
                confidence = (
                    0.97 if selected and supporting_match
                    else 0.94 if selected
                    else 0.7
                )
            else:
                action = FleetSyncAction.NO_CHANGE
                reason = "Il workbook coincide con lo stato persistito."
                selected = False
                confidence = 1.0
        if plate:
            seen_plates.add(plate)
        items.append(
            FleetSyncItem(
                row_id=offset,
                excel_row=profile.row_numbers[offset],
                external_identifier=external,
                plate=plate,
                current=current,
                proposed=proposed,
                difference=difference,
                confidence=confidence,
                action=action,
                interpretation=interpretation,
                reason=reason,
                selected_by_default=selected,
                sensitive_fields=sensitive_fields,
            )
        )

    summary = FleetSyncSummary(
        total_rows=len(items),
        new_assets=sum(item.action is FleetSyncAction.NEW_ASSET for item in items),
        updated_assets=sum(item.action is FleetSyncAction.UPDATE_EXISTING for item in items),
        unchanged_assets=sum(item.action is FleetSyncAction.NO_CHANGE for item in items),
        unavailable_assets=sum(item.proposed.get("availability") == "unavailable" for item in items),
        maintenance_assets=sum(item.proposed.get("availability") == "maintenance" for item in items),
        reserve_assets=sum(item.proposed.get("availability") == "reserve" for item in items),
        possible_duplicates=sum(item.action is FleetSyncAction.POSSIBLE_DUPLICATE for item in items),
        conflicts=sum(item.action is FleetSyncAction.CONFLICT for item in items),
        invalid_rows=sum(item.action is FleetSyncAction.INVALID_ROW for item in items),
        sensitive_fields_excluded=sum(len(item.sensitive_fields) for item in items),
    )
    mappings = []
    for item in profile.mapping:
        sensitive = item.source_column in sensitive_columns
        mappings.append({
            "source_column": item.source_column,
            "target_field": None if sensitive else item.target_field,
            "confidence": 0.0 if sensitive else item.confidence,
            "status": "SENSITIVE" if sensitive else item.status.upper(),
        })
    return FleetSyncPreview(
        fingerprint=sha256(content).hexdigest(),
        original_filename=filename,
        profiled_sheets=len(profile.sheet_profiles),
        selected_sheet=profile.selected_sheet.name,
        selected_header_row=profile.selected_header.row_index,
        source_rows=len(profile.table_rows),
        mappings=mappings,
        summary=summary,
        items=items,
    )

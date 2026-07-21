import json
from hashlib import sha256

from app.core.database import db_session
from app.plugins.fleet.domain.models import AssetEventType, availability_event_type
from app.plugins.fleet.domain.sync_models import (
    FleetSyncAction,
    FleetSyncPreview,
    FleetSyncResult,
)
from app.plugins.fleet.domain.errors import FleetSyncSelectionError
from app.utils.date_utils import utc_now_iso


def metadata_by_asset() -> dict[int, dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM fleet_asset_metadata").fetchall()
    return {
        int(row["asset_id"]): {
            key: row[key]
            for key in row.keys()
            if key not in {"asset_id", "alternative_identifiers"}
        } | {"alternative_identifiers": json.loads(row["alternative_identifiers"])}
        for row in rows
    }


def latest_sync() -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT imported_at, original_filename, summary FROM fleet_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {
        "imported_at": row["imported_at"],
        "original_filename": row["original_filename"],
        "summary": json.loads(row["summary"]),
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _application_key(preview: FleetSyncPreview, selected_rows: list[int]) -> str:
    selected = [
        item.model_dump(mode="json")
        for item in preview.items
        if item.row_id in selected_rows
    ]
    canonical = f"{preview.fingerprint}:{_json(selected)}"
    return sha256(canonical.encode()).hexdigest()


def _append_event(conn, asset_id: int, event_type: AssetEventType, actor: str, details: dict[str, object], now: str, seed: str) -> bool:
    fingerprint = sha256(
        f"{seed}:{asset_id}:{event_type.value}:{_json(details)}".encode()
    ).hexdigest()
    existing = conn.execute(
        "SELECT event_id FROM fleet_sync_event_fingerprints WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    if existing:
        return False
    cursor = conn.execute(
        """
        INSERT INTO fleet_asset_events (
            asset_id, event_type, occurred_at, actor, details, contract_version
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (asset_id, event_type.value, now, actor, _json(details), "1.0"),
    )
    conn.execute(
        "INSERT INTO fleet_sync_event_fingerprints (fingerprint, event_id) VALUES (?, ?)",
        (fingerprint, int(cursor.lastrowid)),
    )
    return True


def _find_asset(conn, external_identifier: str, plate: str):
    return conn.execute(
        """
        SELECT * FROM fleet_assets
        WHERE lower(external_identifier) = lower(?) OR plate = ?
        ORDER BY CASE WHEN lower(external_identifier) = lower(?) THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (external_identifier, plate, external_identifier),
    ).fetchone()


def _metadata_values(proposed: dict[str, object]) -> dict[str, object]:
    return {
        field: proposed.get(field)
        for field in (
            "vehicle_model", "rental_company", "observed_assigned_human_resource",
            "observed_second_human_resource", "replacement_asset_reference",
            "parking_location", "source_reference",
        )
    }


def _upsert_metadata(conn, asset_id: int, proposed: dict[str, object], now: str) -> dict[str, object]:
    row = conn.execute("SELECT * FROM fleet_asset_metadata WHERE asset_id = ?", (asset_id,)).fetchone()
    incoming = _metadata_values(proposed)
    values = dict(incoming)
    alternative_identifiers: list[str] = []
    if row:
        alternative_identifiers = json.loads(row["alternative_identifiers"])
        previous_alternative_identifiers = list(alternative_identifiers)
        previous = {field: row[field] for field in values}
        values = {
            field: (
                incoming[field]
                if incoming[field] is not None or field == "source_reference"
                else previous[field]
            )
            for field in incoming
        }
        external = proposed.get("external_identifier")
        asset = conn.execute("SELECT external_identifier FROM fleet_assets WHERE id = ?", (asset_id,)).fetchone()
        if external and external != asset["external_identifier"] and external not in alternative_identifiers:
            alternative_identifiers.append(str(external))
        conn.execute(
            """
            UPDATE fleet_asset_metadata
            SET vehicle_model = ?, rental_company = ?,
                observed_assigned_human_resource = ?, observed_second_human_resource = ?,
                replacement_asset_reference = ?, parking_location = ?,
                alternative_identifiers = ?, source_reference = ?, updated_at = ?
            WHERE asset_id = ?
            """,
            (
                values["vehicle_model"], values["rental_company"],
                values["observed_assigned_human_resource"], values["observed_second_human_resource"],
                values["replacement_asset_reference"], values["parking_location"],
                _json(alternative_identifiers), values["source_reference"], now, asset_id,
            ),
        )
        changes = {
            field: {"before": previous.get(field), "after": values.get(field)}
            for field in values
            if field != "source_reference" and previous.get(field) != values.get(field)
        }
        if alternative_identifiers != previous_alternative_identifiers:
            changes["alternative_identifiers"] = {
                "before": previous_alternative_identifiers,
                "after": alternative_identifiers,
            }
        return changes
    conn.execute(
        """
        INSERT INTO fleet_asset_metadata (
            asset_id, vehicle_model, rental_company,
            observed_assigned_human_resource, observed_second_human_resource,
            replacement_asset_reference, parking_location, alternative_identifiers,
            source_reference, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id, values["vehicle_model"], values["rental_company"],
            values["observed_assigned_human_resource"], values["observed_second_human_resource"],
            values["replacement_asset_reference"], values["parking_location"],
            "[]", values["source_reference"], now,
        ),
    )
    return {field: {"before": None, "after": value} for field, value in values.items() if field != "source_reference" and value}


def _add_document(conn, asset_id: int, proposed: dict[str, object], actor: str, now: str, seed: str) -> tuple[int, int]:
    expiry = proposed.get("document_expiry")
    if not expiry:
        return 0, 0
    document_type = str(proposed.get("document_type") or "observed_expiration")
    existing = conn.execute(
        """
        SELECT id FROM fleet_asset_documents
        WHERE asset_id = ? AND document_type = ? AND expires_on = ?
        """,
        (asset_id, document_type, expiry),
    ).fetchone()
    if existing:
        return 0, 0
    cursor = conn.execute(
        """
        INSERT INTO fleet_asset_documents (
            asset_id, document_type, name, reference, issued_on,
            expires_on, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (asset_id, document_type, "Documento osservato da registro Fleet", None, None, expiry, None, now),
    )
    event = _append_event(
        conn, asset_id, AssetEventType.ASSET_DOCUMENT_OBSERVED, actor,
        {"document_id": int(cursor.lastrowid), "document_type": document_type, "expires_on": expiry},
        now, seed,
    )
    return 1, int(event)


def _apply_item(conn, item, actor: str, now: str, seed: str) -> tuple[str, int, int]:
    proposed = item.proposed
    external = str(proposed["external_identifier"])
    plate = str(proposed["plate"])
    row = _find_asset(conn, external, plate)
    events = 0
    documents = 0
    if not row:
        cursor = conn.execute(
            """
            INSERT INTO fleet_assets (
                external_identifier, plate, category, status, availability,
                notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (external, plate, proposed.get("category"), proposed["status"], proposed["availability"], None, "[]", now, now),
        )
        asset_id = int(cursor.lastrowid)
        events += int(_append_event(
            conn, asset_id, AssetEventType.ASSET_CREATED, actor,
            {"external_identifier": external, "status": proposed["status"], "availability": proposed["availability"]},
            now, seed,
        ))
        outcome = "created"
    else:
        asset_id = int(row["id"])
        changes = {
            field: {"before": row[field], "after": proposed.get(field)}
            for field in ("plate", "category", "status", "availability")
            if proposed.get(field) is not None and row[field] != proposed.get(field)
        }
        if changes:
            conn.execute(
                """
                UPDATE fleet_assets SET plate = ?, category = ?, status = ?,
                    availability = ?, updated_at = ? WHERE id = ?
                """,
                (
                    proposed.get("plate") or row["plate"], proposed.get("category"),
                    proposed.get("status") or row["status"], proposed.get("availability") or row["availability"],
                    now, asset_id,
                ),
            )
            non_availability = {key: value for key, value in changes.items() if key != "availability"}
            if non_availability:
                events += int(_append_event(
                    conn, asset_id, AssetEventType.ASSET_UPDATED, actor,
                    {"changes": non_availability}, now, seed,
                ))
            if "availability" in changes:
                event_type = availability_event_type(str(row["availability"]), str(proposed["availability"]))
                if proposed["availability"] == "reserve":
                    event_type = AssetEventType.ASSET_RESERVE_ASSIGNED
                events += int(_append_event(
                    conn, asset_id, event_type, actor,
                    {"previous": row["availability"], "current": proposed["availability"]}, now, seed,
                ))
            outcome = "updated"
        else:
            outcome = "unchanged"

    association_changes = _upsert_metadata(conn, asset_id, proposed, now)
    if association_changes:
        events += int(_append_event(
            conn, asset_id, AssetEventType.ASSET_ASSOCIATION_CHANGED, actor,
            {"changes": association_changes}, now, seed,
        ))
        if outcome == "unchanged":
            outcome = "updated"
    document_count, document_events = _add_document(conn, asset_id, proposed, actor, now, seed)
    documents += document_count
    events += document_events
    if document_count and outcome == "unchanged":
        outcome = "updated"
    return outcome, events, documents


def _snapshot_rows(conn) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT a.*, m.observed_assigned_human_resource,
               m.observed_second_human_resource, m.vehicle_model
        FROM fleet_assets a
        LEFT JOIN fleet_asset_metadata m ON m.asset_id = a.id
        ORDER BY a.id
        """
    ).fetchall()
    legacy_status = {
        "maintenance": "manutenzione",
        "unavailable": "non disponibile",
        "reserve": "riserva",
        "available": "available",
    }
    return [
        {
            "row_number": index + 2,
            "vehicle_plate": row["plate"],
            "driver_name": row["observed_assigned_human_resource"],
            "driver_key": None,
            "second_driver_name": row["observed_second_human_resource"],
            "second_driver_key": None,
            "status": legacy_status.get(row["availability"], row["availability"]),
            "station": None,
            "workshop": "officina" if row["availability"] == "maintenance" else None,
            "notes": None,
            "key_available": None,
            "fuel_card": None,
            "vehicle_model": row["vehicle_model"] or row["category"],
            "expirations": None,
            "raw": {},
        }
        for index, row in enumerate(rows)
    ]


def apply_sync(preview: FleetSyncPreview, selected_rows: list[int], actor: str) -> FleetSyncResult:
    allowed_actions = {FleetSyncAction.NEW_ASSET, FleetSyncAction.UPDATE_EXISTING, FleetSyncAction.NO_CHANGE}
    by_id = {item.row_id: item for item in preview.items}
    if len(selected_rows) != len(set(selected_rows)) or any(row_id not in by_id for row_id in selected_rows):
        raise FleetSyncSelectionError("La selezione contiene righe non valide.")
    if any(by_id[row_id].action not in allowed_actions for row_id in selected_rows):
        raise FleetSyncSelectionError("Conflitti, duplicati e righe invalide non possono essere applicati.")
    key = _application_key(preview, selected_rows)
    now = utc_now_iso()
    with db_session() as conn:
        prior_workbook = conn.execute(
            "SELECT import_id FROM fleet_sync_runs "
            "WHERE workbook_fingerprint = ? ORDER BY id DESC LIMIT 1",
            (preview.fingerprint,),
        ).fetchone()
        selected_items = [by_id[row_id] for row_id in selected_rows]
        if prior_workbook and all(
            item.action is FleetSyncAction.NO_CHANGE
            for item in selected_items
        ):
            return FleetSyncResult(
                fingerprint=preview.fingerprint,
                import_id=int(prior_workbook["import_id"]),
                idempotent=True,
                created_assets=0,
                updated_assets=0,
                unchanged_assets=(
                    len(selected_items)
                    if selected_items
                    else preview.summary.unchanged_assets
                ),
                events_created=0,
                documents_created=0,
                selected_rows=len(selected_items),
                unresolved_conflicts=(
                    preview.summary.conflicts
                    + preview.summary.possible_duplicates
                ),
            )
        prior = conn.execute("SELECT import_id, summary FROM fleet_sync_runs WHERE application_key = ?", (key,)).fetchone()
        if prior:
            return FleetSyncResult(
                fingerprint=preview.fingerprint,
                import_id=int(prior["import_id"]),
                idempotent=True,
                **json.loads(prior["summary"]),
            )
        created = updated = unchanged = events = documents = 0
        for row_id in selected_rows:
            outcome, item_events, item_documents = _apply_item(conn, by_id[row_id], actor, now, key)
            created += outcome == "created"
            updated += outcome == "updated"
            unchanged += outcome == "unchanged"
            events += item_events
            documents += item_documents
        snapshot = _snapshot_rows(conn)
        cursor = conn.execute(
            """
            INSERT INTO imports (
                dataset_type, original_filename, imported_at, sheet_name,
                column_mapping, normalized_rows
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "fleet", preview.original_filename, now, preview.selected_sheet,
                _json(preview.mappings), _json(snapshot),
            ),
        )
        import_id = int(cursor.lastrowid)
        result_values = {
            "created_assets": int(created), "updated_assets": int(updated),
            "unchanged_assets": int(unchanged), "events_created": events,
            "documents_created": documents, "selected_rows": len(selected_rows),
            "unresolved_conflicts": (
                preview.summary.conflicts + preview.summary.possible_duplicates
            ),
        }
        conn.execute(
            """
            INSERT INTO fleet_sync_runs (
                application_key, workbook_fingerprint, original_filename,
                imported_at, import_id, summary
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, preview.fingerprint, preview.original_filename, now, import_id, _json(result_values)),
        )
    return FleetSyncResult(
        fingerprint=preview.fingerprint,
        import_id=import_id,
        **result_values,
    )

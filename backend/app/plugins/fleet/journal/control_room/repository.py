from app.core.database import db_session


def list_procedures() -> list[dict]:
    with db_session() as conn:
        movements = conn.execute(
            """
            SELECT m.*, a.category AS vehicle_model,
                   s.source, s.lifecycle_status, s.scheduled_at,
                   s.opened_at, s.in_progress_at,
                   d.id AS damage_case_id, d.case_number AS damage_case_number,
                   d.status AS damage_case_status
            FROM asset_movements m
            JOIN journal_sessions s ON s.id = m.session_id
            JOIN fleet_assets a ON a.id = m.asset_id
            LEFT JOIN damage_cases d ON d.source_movement_id = m.id
            ORDER BY m.occurred_at DESC, m.created_at DESC
            """
        ).fetchall()
        open_sessions = conn.execute(
            """
            SELECT s.id, s.asset_id, s.plate_snapshot,
                   s.declared_driver_identifier, s.operation_type,
                   s.operational_shift, s.created_at, s.expires_at,
                   s.source, s.lifecycle_status, s.scheduled_at,
                   s.opened_at, s.in_progress_at,
                   a.category AS vehicle_model
            FROM journal_sessions s
            JOIN fleet_assets a ON a.id = s.asset_id
            WHERE s.status = 'open'
            ORDER BY s.created_at DESC
            """
        ).fetchall()
        movement_ids = [row["id"] for row in movements]
        equipment: dict[str, list[dict]] = {key: [] for key in movement_ids}
        media: dict[str, list[dict]] = {key: [] for key in movement_ids}
        if movement_ids:
            placeholders = ",".join("?" for _ in movement_ids)
            for row in conn.execute(
                f"""SELECT movement_id, equipment_code, equipment_label_snapshot,
                           equipment_status, note
                    FROM movement_equipment WHERE movement_id IN ({placeholders})
                    ORDER BY movement_id, equipment_label_snapshot""",
                movement_ids,
            ).fetchall():
                equipment[row["movement_id"]].append({key: row[key] for key in row.keys()})
            for row in conn.execute(
                f"""SELECT id, movement_id, media_type, verified_mime_type,
                           size_bytes, display_order
                    FROM movement_media WHERE movement_id IN ({placeholders})
                    ORDER BY movement_id, display_order""",
                movement_ids,
            ).fetchall():
                item = {key: row[key] for key in row.keys()}
                item["url"] = f"/api/plugins/fleet/v1/journal/media/{row['id']}"
                media[row["movement_id"]].append(item)
    result = []
    for row in movements:
        item = {key: row[key] for key in row.keys()}
        item["equipment"] = equipment[row["id"]]
        item["media"] = media[row["id"]]
        result.append(item)
    for row in open_sessions:
        item = {key: row[key] for key in row.keys()}
        item["incomplete"] = True
        item["equipment"] = []
        item["media"] = []
        result.append(item)
    return result


def get_procedure(procedure_id: str) -> dict | None:
    return next((item for item in list_procedures() if item["id"] == procedure_id), None)

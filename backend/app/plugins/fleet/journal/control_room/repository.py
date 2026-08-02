from app.core.database import db_session


def sessions_without_operational_date(organization_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT s.id,
                   COALESCE(m.occurred_at, s.scheduled_at, s.opened_at, s.created_at) AS reference_at
            FROM journal_sessions s
            LEFT JOIN asset_movements m ON m.session_id = s.id
            WHERE s.organization_id = ? AND s.operational_date IS NULL
            """,
            (organization_id,),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def set_operational_date(session_id: str, operational_day: str) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE journal_sessions SET operational_date = ? WHERE id = ? AND operational_date IS NULL",
            (operational_day, session_id),
        )


def month_counts(organization_id: str, start_date: str, end_date: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            WITH procedures AS (
                SELECT s.operational_date AS operational_date,
                       CASE WHEN m.anomaly_present = 1 THEN 1 ELSE 0 END AS anomaly,
                       0 AS incomplete,
                       CASE WHEN EXISTS (
                           SELECT 1 FROM movement_media mm WHERE mm.movement_id = m.id
                       ) THEN 1 ELSE 0 END AS with_media
                FROM asset_movements m
                JOIN journal_sessions s ON s.id = m.session_id
                WHERE m.organization_id = ?
                  AND s.operational_date BETWEEN ? AND ?
                UNION ALL
                SELECT s.operational_date,
                       0 AS anomaly,
                       1 AS incomplete,
                       CASE WHEN EXISTS (
                           SELECT 1 FROM movement_media mm WHERE mm.session_id = s.id
                       ) THEN 1 ELSE 0 END AS with_media
                FROM journal_sessions s
                WHERE s.organization_id = ? AND s.status = 'open'
                  AND s.operational_date BETWEEN ? AND ?
            )
            SELECT operational_date AS date,
                   COUNT(*) AS total,
                   SUM(anomaly) AS anomalies,
                   SUM(incomplete) AS incomplete,
                   SUM(with_media) AS with_media
            FROM procedures
            GROUP BY operational_date
            ORDER BY operational_date
            """,
            (organization_id, start_date, end_date, organization_id, start_date, end_date),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def list_procedures(
    organization_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    range_clause = ""
    range_params: list[object] = []
    if start_date and end_date:
        range_clause = " AND s.operational_date BETWEEN ? AND ?"
        range_params = [start_date, end_date]
    with db_session() as conn:
        movements = conn.execute(
            f"""
            SELECT m.*, a.category AS vehicle_model,
                   s.source, s.lifecycle_status, s.scheduled_at,
                   s.opened_at, s.in_progress_at, s.driver_name,
                   s.driver_surname, s.warnings_json, s.operational_date,
                   d.id AS damage_case_id, d.case_number AS damage_case_number,
                   d.status AS damage_case_status
            FROM asset_movements m
            JOIN journal_sessions s ON s.id = m.session_id
            JOIN fleet_assets a ON a.id = m.asset_id
            LEFT JOIN damage_cases d ON d.source_movement_id = m.id
            WHERE m.organization_id = ? {range_clause}
            ORDER BY m.occurred_at DESC, m.created_at DESC
            """, (organization_id, *range_params)
        ).fetchall()
        open_sessions = conn.execute(
            f"""
            SELECT s.id, s.asset_id, s.plate_snapshot,
                   s.declared_driver_identifier, s.operation_type,
                   s.operational_shift, s.created_at, s.expires_at,
                   s.source, s.lifecycle_status, s.scheduled_at,
                   s.opened_at, s.in_progress_at, s.driver_name,
                   s.driver_surname, s.warnings_json, s.operational_date,
                   a.category AS vehicle_model
            FROM journal_sessions s
            JOIN fleet_assets a ON a.id = s.asset_id
            WHERE s.status = 'open'
              AND s.organization_id = ?
              {"AND s.operational_date BETWEEN ? AND ?" if start_date and end_date else ""}
            ORDER BY s.created_at DESC
            """, (organization_id, *range_params)
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
                item["url"] = f"/api/fleet/journal-control-room/media/{row['id']}"
                item["download_url"] = f"/api/fleet/journal-control-room/media/{row['id']}?download=1"
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


def get_procedure(procedure_id: str, organization_id: str) -> dict | None:
    return next((item for item in list_procedures(organization_id) if item["id"] == procedure_id), None)

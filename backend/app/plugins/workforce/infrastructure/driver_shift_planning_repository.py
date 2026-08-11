import json
from collections.abc import Sequence

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningError,
    DriverShiftPlanningConflictError,
    DriverShiftPlanningPublication,
    DriverShiftPlanningResolution,
    DriverShiftPlanningNotFoundError,
    DriverShiftPlanningSource,
    DriverShiftPlanningSourceNotFoundError,
    DriverShiftPlanningStatus,
)
from app.utils.date_utils import utc_now_iso


def _planning(row) -> DriverShiftPlanning:
    return DriverShiftPlanning.model_validate({key: row[key] for key in row.keys()})


def _resolution(row) -> DriverShiftPlanningResolution:
    values = {key: row[key] for key in row.keys()}
    values["resolved_payload"] = (
        json.loads(values["resolved_payload"]) if values["resolved_payload"] else None
    )
    return DriverShiftPlanningResolution.model_validate(values)


def _source(row) -> DriverShiftPlanningSource:
    date_from = row["date_from"]
    date_to = row["date_to"]
    period_start = row["period_start"]
    period_end = row["period_end"]
    warnings: list[str] = []
    if row["status"] == "UNAVAILABLE_FOR_MERGE":
        compatibility = "UNAVAILABLE"
        warnings.append("La source non dispone di righe immutabili per il merge.")
    elif date_from < period_start or date_to > period_end:
        compatibility = "PARTIAL_OVERLAP"
        warnings.append("La source copre solo parzialmente il periodo del planning.")
    else:
        compatibility = "COMPATIBLE"
    return DriverShiftPlanningSource.model_validate({
        "id": row["id"],
        "organization_id": row["organization_id"],
        "driver_shift_planning_id": row["driver_shift_planning_id"],
        "workforce_import_id": row["workforce_import_id"],
        "source_filename": row["source_filename"],
        "imported_at": row["imported_at"],
        "row_count": int(row["row_count"] or 0),
        "source_order": row["source_order"],
        "added_at": row["added_at"],
        "added_by": row["added_by"],
        "status": row["status"],
        "date_from": date_from,
        "date_to": date_to,
        "period_compatibility": compatibility,
        "warnings": warnings,
    })


def create_planning(
    organization_id: str,
    period_start: str,
    period_end: str,
    label: str | None,
    actor: str,
) -> DriverShiftPlanning:
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status,
                version, created_at, created_by, updated_at
            ) VALUES (?, ?, ?, ?, 'DRAFT', 1, ?, ?, ?)
            """,
            (organization_id, label, period_start, period_end, now, actor, now),
        )
        row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (cursor.lastrowid, organization_id),
        ).fetchone()
    assert row is not None
    return _planning(row)


def get_planning(organization_id: str, planning_id: int) -> DriverShiftPlanning:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
    if row is None:
        raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
    return _planning(row)


def list_plannings(organization_id: str) -> list[DriverShiftPlanning]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM driver_shift_plannings
            WHERE organization_id = ?
            ORDER BY
                CASE status
                    WHEN 'DRAFT' THEN 0
                    WHEN 'ACTIVE' THEN 1
                    ELSE 2
                END,
                updated_at DESC,
                id DESC
            """,
            (organization_id,),
        ).fetchall()
    return [_planning(row) for row in rows]


def source_facts(organization_id: str, workforce_import_id: int) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT i.id, i.original_filename,
                   COUNT(r.id) AS source_row_count,
                   MIN(r.operational_date) AS date_from,
                   MAX(r.operational_date) AS date_to
            FROM workforce_imports i
            LEFT JOIN workforce_import_rows r
              ON r.workforce_import_id = i.id
             AND r.organization_id = i.organization_id
             AND r.row_kind = 'shift'
             AND r.operational_date IS NOT NULL
            WHERE i.id = ? AND i.organization_id = ?
            GROUP BY i.id, i.original_filename
            """,
            (workforce_import_id, organization_id),
        ).fetchone()
    return ({key: row[key] for key in row.keys()} if row else None)


def import_reference_by_fingerprint(
    organization_id: str,
    fingerprint: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id AS workforce_import_id, fingerprint,
                   original_filename, imported_at
            FROM workforce_imports
            WHERE organization_id = ? AND fingerprint = ?
            """,
            (organization_id, fingerprint),
        ).fetchone()
    return ({key: row[key] for key in row.keys()} if row else None)


def list_sources(
    organization_id: str,
    planning_id: int,
) -> list[DriverShiftPlanningSource]:
    get_planning(organization_id, planning_id)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT s.*, i.original_filename AS source_filename,
                   i.imported_at,
                   COUNT(r.id) AS row_count,
                   MIN(r.operational_date) AS date_from,
                   MAX(r.operational_date) AS date_to,
                   p.period_start, p.period_end
            FROM driver_shift_planning_sources s
            JOIN driver_shift_plannings p
              ON p.id = s.driver_shift_planning_id
             AND p.organization_id = s.organization_id
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            LEFT JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
             AND r.row_kind = 'shift'
             AND r.operational_date IS NOT NULL
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
            GROUP BY s.id, s.organization_id, s.driver_shift_planning_id,
                     s.workforce_import_id, s.source_order, s.added_at,
                     s.added_by, s.status, i.original_filename, i.imported_at,
                     p.period_start, p.period_end
            ORDER BY s.source_order, s.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [_source(row) for row in rows]


def add_source_record(
    organization_id: str,
    planning_id: int,
    workforce_import_id: int,
    source_order: int,
    status: str,
    actor: str,
) -> int:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        existing = conn.execute(
            """
            SELECT id FROM driver_shift_planning_sources
            WHERE organization_id = ? AND driver_shift_planning_id = ?
              AND workforce_import_id = ?
            """,
            (organization_id, planning_id, workforce_import_id),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_planning_sources (
                organization_id, driver_shift_planning_id,
                workforce_import_id, source_order, added_at, added_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id, planning_id, workforce_import_id,
                source_order, now, actor, status,
            ),
        )
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )
        return int(cursor.lastrowid)


def remove_source_record(
    organization_id: str,
    planning_id: int,
    source_id: int,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        cursor = conn.execute(
            """
            DELETE FROM driver_shift_planning_sources
            WHERE id = ? AND driver_shift_planning_id = ? AND organization_id = ?
            """,
            (source_id, planning_id, organization_id),
        )
        if cursor.rowcount == 0:
            raise DriverShiftPlanningSourceNotFoundError("Source del planning non trovata.")
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )


def replace_source_records(
    organization_id: str,
    planning_id: int,
    sources: Sequence[tuple[int, int, str]],
    actor: str,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError(
                "Le source possono essere modificate solo in DRAFT."
            )
        conn.execute(
            "DELETE FROM driver_shift_planning_sources WHERE organization_id = ? AND driver_shift_planning_id = ?",
            (organization_id, planning_id),
        )
        conn.executemany(
            """
            INSERT INTO driver_shift_planning_sources (
                organization_id, driver_shift_planning_id,
                workforce_import_id, source_order, added_at, added_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (organization_id, planning_id, import_id, order, now, actor, status)
                for import_id, order, status in sources
            ],
        )
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET version = version + 1, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, planning_id, organization_id),
        )


def merge_rows(organization_id: str, planning_id: int) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT r.*, i.original_filename AS source_filename,
                   s.source_order
            FROM driver_shift_planning_sources s
            JOIN driver_shift_plannings p
              ON p.id = s.driver_shift_planning_id
             AND p.organization_id = s.organization_id
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
              AND s.status = 'AVAILABLE'
              AND r.row_kind = 'shift'
              AND r.operational_date IS NOT NULL
              AND r.operational_date BETWEEN p.period_start AND p.period_end
            ORDER BY s.source_order, s.id, r.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def list_identity_rows_for_logical_planning(
    organization_id: str,
    planning_id: int,
) -> list[dict[str, object]]:
    get_planning(organization_id, planning_id)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT r.*, i.original_filename AS source_filename,
                   s.source_order
            FROM driver_shift_planning_sources s
            JOIN workforce_imports i
              ON i.id = s.workforce_import_id
             AND i.organization_id = s.organization_id
            JOIN workforce_import_rows r
              ON r.workforce_import_id = s.workforce_import_id
             AND r.organization_id = s.organization_id
            WHERE s.organization_id = ?
              AND s.driver_shift_planning_id = ?
              AND r.row_kind = 'identity'
            ORDER BY s.source_order, s.id, r.id
            """,
            (organization_id, planning_id),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def list_resolutions(
    organization_id: str,
    planning_id: int,
    planning_version: int,
) -> list[DriverShiftPlanningResolution]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM driver_shift_planning_resolutions
            WHERE organization_id = ? AND driver_shift_planning_id = ?
              AND planning_version = ?
            ORDER BY updated_at, id
            """,
            (organization_id, planning_id, planning_version),
        ).fetchall()
    return [_resolution(row) for row in rows]


def upsert_resolution(
    organization_id: str,
    planning_id: int,
    expected_version: int,
    conflict_key: str,
    resolution_type: str,
    selected_source_row_id: int | None,
    resolved_payload: dict[str, object] | None,
    actor: str,
) -> DriverShiftPlanningResolution:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT status, version FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if int(planning["version"]) != expected_version:
            raise DriverShiftPlanningConflictError("Il planning è cambiato: ricarica la preview.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError("Le risoluzioni possono essere modificate solo in DRAFT.")
        existing = conn.execute(
            """
            SELECT id, created_at FROM driver_shift_planning_resolutions
            WHERE organization_id = ? AND driver_shift_planning_id = ?
              AND planning_version = ? AND conflict_key = ?
            """,
            (organization_id, planning_id, expected_version, conflict_key),
        ).fetchone()
        payload_json = json.dumps(resolved_payload, ensure_ascii=False, sort_keys=True) if resolved_payload else None
        if existing:
            resolution_id = int(existing["id"])
            conn.execute(
                """
                UPDATE driver_shift_planning_resolutions
                SET resolution_type = ?, selected_source_row_id = ?,
                    resolved_payload = ?, actor = ?, updated_at = ?
                WHERE id = ? AND organization_id = ?
                """,
                (resolution_type, selected_source_row_id, payload_json, actor, now, resolution_id, organization_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO driver_shift_planning_resolutions (
                    organization_id, driver_shift_planning_id, planning_version,
                    conflict_key, resolution_type, selected_source_row_id,
                    resolved_payload, actor, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (organization_id, planning_id, expected_version, conflict_key,
                 resolution_type, selected_source_row_id, payload_json, actor, now, now),
            )
            resolution_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("driver_shift_planning", str(planning_id), actor, now, None,
             json.dumps({"planning_version": expected_version, "conflict_key": conflict_key,
                         "resolution_type": resolution_type,
                         "selected_source_row_id": selected_source_row_id}, ensure_ascii=False),
             "driver_shift_planning_conflict_resolved", "driver_shift_planning", organization_id),
        )
        row = conn.execute(
            "SELECT * FROM driver_shift_planning_resolutions WHERE id = ? AND organization_id = ?",
            (resolution_id, organization_id),
        ).fetchone()
    assert row is not None
    return _resolution(row)


def workforce_member_exists(organization_id: str, member_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT 1 FROM workforce_members WHERE id = ? AND organization_id = ? AND active = 1",
            (member_id, organization_id),
        ).fetchone()
    return row is not None


def valid_workforce_member_ids(
    organization_id: str, member_ids: set[int], chunk_size: int = 500,
) -> set[int]:
    valid: set[int] = set()
    ordered = sorted(member_ids)
    with db_session() as conn:
        for offset in range(0, len(ordered), chunk_size):
            chunk = ordered[offset:offset + chunk_size]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""SELECT id FROM workforce_members
                    WHERE organization_id = ? AND active = 1
                      AND id IN ({placeholders})""",
                (organization_id, *chunk),
            ).fetchall()
            valid.update(int(row["id"]) for row in rows)
    return valid


def raw_row_belongs_to_planning(
    organization_id: str, planning_id: int, row_id: int,
) -> bool:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM workforce_import_rows r
            JOIN driver_shift_planning_sources s
              ON s.workforce_import_id = r.workforce_import_id
             AND s.organization_id = r.organization_id
            WHERE r.id = ? AND r.organization_id = ?
              AND s.driver_shift_planning_id = ? AND s.status = 'AVAILABLE'
            """,
            (row_id, organization_id, planning_id),
        ).fetchone()
    return row is not None


def create_revision(
    organization_id: str, planning_id: int, actor: str,
) -> DriverShiftPlanning:
    now = utc_now_iso()
    with db_session() as conn:
        original = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if original is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if original["status"] != DriverShiftPlanningStatus.ACTIVE.value:
            raise DriverShiftPlanningError("Una nuova revisione nasce da un planning ACTIVE.")
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status,
                version, created_at, created_by, updated_at, revision_of_planning_id
            ) VALUES (?, ?, ?, ?, 'DRAFT', 1, ?, ?, ?, ?)
            """,
            (organization_id, original["label"], original["period_start"],
             original["period_end"], now, actor, now, planning_id),
        )
        revision_id = int(cursor.lastrowid)
        sources = conn.execute(
            """
            SELECT workforce_import_id, source_order, status
            FROM driver_shift_planning_sources
            WHERE organization_id = ? AND driver_shift_planning_id = ?
            ORDER BY source_order, id
            """,
            (organization_id, planning_id),
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO driver_shift_planning_sources (
                organization_id, driver_shift_planning_id, workforce_import_id,
                source_order, added_at, added_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(organization_id, revision_id, row["workforce_import_id"], row["source_order"],
              now, actor, row["status"]) for row in sources],
        )
        row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (revision_id, organization_id),
        ).fetchone()
    assert row is not None
    return _planning(row)


def _apply_canonical_statuses(conn, organization_id: str, planning, projection, now: str) -> None:
    new_member_ids = {int(item["workforce_member_id"]) for item in projection}
    source_members = conn.execute(
        """
        SELECT DISTINCT r.resolved_workforce_member_id AS workforce_member_id
        FROM workforce_import_rows r
        JOIN driver_shift_planning_sources s
          ON s.workforce_import_id = r.workforce_import_id
         AND s.organization_id = r.organization_id
        WHERE s.organization_id = ? AND s.driver_shift_planning_id = ?
          AND r.row_kind = 'shift' AND r.resolved_workforce_member_id IS NOT NULL
          AND r.operational_date BETWEEN ? AND ?
        """,
        (organization_id, planning["id"], planning["period_start"], planning["period_end"]),
    ).fetchall()
    previous_rows = conn.execute(
        """
        SELECT pr.workforce_member_id
        FROM driver_shift_planning_published_rows pr
        JOIN driver_shift_plannings p ON p.id = pr.driver_shift_planning_id
          AND p.organization_id = pr.organization_id
        WHERE pr.organization_id = ? AND p.period_start = ? AND p.period_end = ?
          AND p.status = 'ACTIVE'
        """,
        (organization_id, planning["period_start"], planning["period_end"]),
    ).fetchall()
    affected = (
        new_member_ids
        | {int(row["workforce_member_id"]) for row in previous_rows}
        | {int(row["workforce_member_id"]) for row in source_members}
    )
    if affected:
        placeholders = ",".join("?" for _ in affected)
        conn.execute(
            f"""DELETE FROM workforce_day_statuses
                WHERE organization_id = ? AND date BETWEEN ? AND ?
                  AND workforce_member_id IN ({placeholders})""",
            (organization_id, planning["period_start"], planning["period_end"], *sorted(affected)),
        )
    source_reference = f"driver_shift_planning:{planning['id']}:v{planning['version']}"
    conn.executemany(
        """
        INSERT INTO workforce_day_statuses (
            workforce_member_id, date, status_code, availability, shift_code,
            start_time, end_time, notes, source_reference,
            observed_or_confirmed, updated_at, organization_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?, ?)
        """,
        [(item["workforce_member_id"], item["operational_date"], item["status_code"],
          int(bool(item["availability"])), item.get("shift_code"), item.get("start_time"),
          item.get("end_time"), item.get("notes"), source_reference, now, organization_id)
         for item in projection],
    )


def publish_projection(
    organization_id: str,
    planning_id: int,
    expected_version: int,
    expected_fingerprint: str,
    current_fingerprint: str,
    projection: list[dict[str, object]],
    actor: str,
) -> DriverShiftPlanningPublication:
    now = utc_now_iso()
    with db_session() as conn:
        planning = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if int(planning["version"]) != expected_version or expected_fingerprint != current_fingerprint:
            raise DriverShiftPlanningConflictError("La preview è cambiata: ricaricala prima di pubblicare.")
        if planning["status"] != DriverShiftPlanningStatus.DRAFT.value:
            raise DriverShiftPlanningError("Può essere pubblicato solo un planning DRAFT.")
        superseded = conn.execute(
            """
            SELECT id FROM driver_shift_plannings
            WHERE organization_id = ? AND status = 'ACTIVE' AND id <> ?
              AND period_start = ? AND period_end = ?
            """,
            (organization_id, planning_id, planning["period_start"], planning["period_end"]),
        ).fetchall()
        superseded_ids = [int(row["id"]) for row in superseded]
        _apply_canonical_statuses(conn, organization_id, planning, projection, now)
        conn.executemany(
            """
            INSERT INTO driver_shift_planning_published_rows (
                organization_id, driver_shift_planning_id, planning_version,
                workforce_member_id, operational_date, status_code, availability,
                shift_code, start_time, end_time, station, transporter_id,
                provenance_summary, selected_source_row_id, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(organization_id, planning_id, expected_version, item["workforce_member_id"],
              item["operational_date"], item["status_code"], int(bool(item["availability"])),
              item.get("shift_code"), item.get("start_time"), item.get("end_time"),
              item.get("station"), item.get("transporter_id"),
              json.dumps(item["provenance_summary"], ensure_ascii=False, sort_keys=True),
              item.get("selected_source_row_id"), now) for item in projection],
        )
        if superseded_ids:
            placeholders = ",".join("?" for _ in superseded_ids)
            conn.execute(
                f"UPDATE driver_shift_plannings SET status = 'SUPERSEDED', updated_at = ? WHERE organization_id = ? AND id IN ({placeholders})",
                (now, organization_id, *superseded_ids),
            )
        conn.execute(
            """UPDATE driver_shift_plannings
               SET status = 'ACTIVE', published_at = ?, published_by = ?, updated_at = ?
               WHERE id = ? AND organization_id = ?""",
            (now, actor, now, planning_id, organization_id),
        )
        audit_rows = []
        for superseded_id in superseded_ids:
            audit_rows.append(("driver_shift_planning", str(superseded_id), actor, now, None,
                               json.dumps({"superseded_by": planning_id}),
                               "driver_shift_planning_superseded", "driver_shift_planning", organization_id))
        audit_rows.append(("driver_shift_planning", str(planning_id), actor, now, None,
                           json.dumps({"version": expected_version, "period_start": planning["period_start"],
                                       "period_end": planning["period_end"], "published_rows": len(projection)},
                                      ensure_ascii=False),
                           "driver_shift_planning_published", "driver_shift_planning", organization_id))
        conn.executemany(
            """INSERT INTO workforce_changes (
                   entity_type, entity_id, actor, timestamp, before_value,
                   after_value, reason, source, organization_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            audit_rows,
        )
        updated = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
    assert updated is not None
    members = {int(item["workforce_member_id"]) for item in projection}
    days = {(int(item["workforce_member_id"]), str(item["operational_date"])) for item in projection}
    return DriverShiftPlanningPublication(
        planning=_planning(updated), published_rows=len(projection),
        published_drivers=len(members), published_days=len(days),
        superseded_planning_ids=superseded_ids, published_at=now,
    )


def list_published_shifts_for_workforce_member(
    organization_id: str, workforce_member_id: int, period_start: str, period_end: str,
) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT pr.* FROM driver_shift_planning_published_rows pr
            JOIN driver_shift_plannings p ON p.id = pr.driver_shift_planning_id
              AND p.organization_id = pr.organization_id
            WHERE pr.organization_id = ? AND pr.workforce_member_id = ?
              AND pr.operational_date BETWEEN ? AND ? AND p.status = 'ACTIVE'
            ORDER BY pr.operational_date, pr.id
            """,
            (organization_id, workforce_member_id, period_start, period_end),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]

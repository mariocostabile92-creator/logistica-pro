import json
from collections.abc import Sequence

from app.core.database import PostgresConnection, db_session
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningConflictError,
    DriverShiftPlanningError,
    DriverShiftPlanningNotFoundError,
    DriverShiftPlanningPublication,
    DriverShiftPlanningPublishBlockedError,
    DriverShiftPlanningStatus,
)
from app.plugins.workforce.domain.legacy_canonical_publication import (
    LEGACY_CANONICAL_PROVENANCE,
    legacy_canonical_fingerprint,
)
from app.utils.date_utils import utc_now_iso


def _planning(row) -> DriverShiftPlanning:
    return DriverShiftPlanning.model_validate({key: row[key] for key in row.keys()})


def _canonical_rows(
    conn,
    organization_id: str,
    period_start: str,
    period_end: str,
    *,
    lock: bool = False,
) -> list[dict[str, object]]:
    lock_clause = " FOR SHARE OF ds" if lock and isinstance(conn, PostgresConnection) else ""
    rows = conn.execute(
        f"""
        SELECT ds.workforce_member_id, ds.date AS operational_date,
               ds.status_code, ds.availability, ds.shift_code, ds.operational_activity,
               ds.start_time, ds.end_time, ds.notes, ds.source_reference
        FROM workforce_day_statuses ds
        JOIN workforce_members m
          ON m.id = ds.workforce_member_id
         AND m.organization_id = ds.organization_id
        WHERE ds.organization_id = ? AND ds.date BETWEEN ? AND ?
        ORDER BY ds.workforce_member_id, ds.date, ds.id{lock_clause}
        """,
        (organization_id, period_start, period_end),
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _source_facts(conn, organization_id: str, planning_id: int) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT s.id) AS sources_total,
               COALESCE(SUM(CASE WHEN s.status = 'AVAILABLE' THEN 1 ELSE 0 END), 0)
                   AS available_sources,
               COUNT(r.id) AS immutable_rows
        FROM driver_shift_planning_sources s
        JOIN driver_shift_plannings p
          ON p.id = s.driver_shift_planning_id
         AND p.organization_id = s.organization_id
        LEFT JOIN workforce_import_rows r
          ON r.workforce_import_id = s.workforce_import_id
         AND r.organization_id = s.organization_id
         AND r.row_kind = 'shift'
         AND r.operational_date BETWEEN p.period_start AND p.period_end
        WHERE s.organization_id = ? AND s.driver_shift_planning_id = ?
        """,
        (organization_id, planning_id),
    ).fetchone()
    assert row is not None
    return {
        "sources_total": int(row["sources_total"] or 0),
        "available_sources": int(row["available_sources"] or 0),
        "immutable_rows": int(row["immutable_rows"] or 0),
    }


def _published_count(conn, organization_id: str, planning_id: int, version: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM driver_shift_planning_published_rows
        WHERE organization_id = ? AND driver_shift_planning_id = ?
          AND planning_version = ?
        """,
        (organization_id, planning_id, version),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def _validate_legacy_source(facts: dict[str, int]) -> None:
    if facts["sources_total"] == 0:
        raise DriverShiftPlanningPublishBlockedError(
            "Il bridge legacy richiede una source legacy collegata."
        )
    if facts["available_sources"] or facts["immutable_rows"]:
        raise DriverShiftPlanningPublishBlockedError(
            "La source dispone di righe immutabili: usa il publish multi-source normale."
        )


def read_preview_context(
    organization_id: str,
    planning_id: int,
) -> tuple[DriverShiftPlanning, list[dict[str, object]], int]:
    with db_session() as conn:
        planning_row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning_row is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        planning = _planning(planning_row)
        if planning.status != DriverShiftPlanningStatus.DRAFT:
            raise DriverShiftPlanningError(
                "La preview legacy e disponibile solo per un planning DRAFT."
            )
        _validate_legacy_source(_source_facts(conn, organization_id, planning_id))
        published = _published_count(conn, organization_id, planning_id, planning.version)
        if published:
            raise DriverShiftPlanningPublishBlockedError(
                "La revisione possiede gia una proiezione pubblicata."
            )
        rows = _canonical_rows(
            conn, organization_id, planning.period_start, planning.period_end
        )
    return planning, rows, published


def _existing_legacy_publication(
    conn,
    organization_id: str,
    planning_row,
    expected_fingerprint: str,
) -> DriverShiftPlanningPublication | None:
    rows = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT workforce_member_id) AS drivers,
               SUM(CASE WHEN provenance_type = ? THEN 0 ELSE 1 END) AS other_provenance,
               MAX(published_at) AS published_at
        FROM driver_shift_planning_published_rows
        WHERE organization_id = ? AND driver_shift_planning_id = ?
          AND planning_version = ?
        """,
        (
            LEGACY_CANONICAL_PROVENANCE,
            organization_id,
            planning_row["id"],
            planning_row["version"],
        ),
    ).fetchone()
    if rows is None or int(rows["total"] or 0) == 0 or int(rows["other_provenance"] or 0):
        return None
    audit = conn.execute(
        """
        SELECT after_value
        FROM workforce_changes
        WHERE organization_id = ? AND entity_type = 'driver_shift_planning'
          AND entity_id = ? AND reason = 'driver_shift_planning_legacy_published'
        ORDER BY id DESC LIMIT 1
        """,
        (organization_id, str(planning_row["id"])),
    ).fetchone()
    payload = json.loads(audit["after_value"]) if audit else {}
    if payload.get("fingerprint") != expected_fingerprint:
        raise DriverShiftPlanningConflictError(
            "La revisione e gia stata pubblicata con una fingerprint differente."
        )
    superseded_ids = [int(item) for item in payload.get("superseded_planning_ids", [])]
    return DriverShiftPlanningPublication(
        planning=_planning(planning_row),
        published_rows=int(rows["total"]),
        published_drivers=int(rows["drivers"] or 0),
        published_days=int(rows["total"]),
        superseded_planning_ids=superseded_ids,
        published_at=str(rows["published_at"]),
    )


def _insert_published_rows(
    conn,
    organization_id: str,
    planning_id: int,
    planning_version: int,
    rows: Sequence[dict[str, object]],
    published_at: str,
) -> None:
    conn.executemany(
        """
        INSERT INTO driver_shift_planning_published_rows (
            organization_id, driver_shift_planning_id, planning_version,
            workforce_member_id, operational_date, status_code, availability,
            shift_code, operational_activity, start_time, end_time, station, transporter_id, notes,
            provenance_type, provenance_summary, selected_source_row_id, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?)
        """,
        [
            (
                organization_id,
                planning_id,
                planning_version,
                row["workforce_member_id"],
                row["operational_date"],
                row["status_code"],
                int(bool(row["availability"])),
                row.get("shift_code"),
                row.get("operational_activity"),
                row.get("start_time"),
                row.get("end_time"),
                row.get("notes"),
                LEGACY_CANONICAL_PROVENANCE,
                json.dumps(
                    [{
                        "provenance_type": LEGACY_CANONICAL_PROVENANCE,
                        "source_reference": row.get("source_reference"),
                    }],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                published_at,
            )
            for row in rows
        ],
    )


def publish_legacy_projection(
    organization_id: str,
    planning_id: int,
    expected_version: int,
    expected_fingerprint: str,
    actor: str,
) -> DriverShiftPlanningPublication:
    now = utc_now_iso()
    with db_session() as conn:
        planning_row = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
        if planning_row is None:
            raise DriverShiftPlanningNotFoundError("Logical planning non trovato.")
        if int(planning_row["version"]) != expected_version:
            raise DriverShiftPlanningConflictError(
                "Il planning e cambiato: ricarica la preview legacy."
            )
        if planning_row["status"] != DriverShiftPlanningStatus.DRAFT.value:
            existing = _existing_legacy_publication(
                conn, organization_id, planning_row, expected_fingerprint
            )
            if existing is not None:
                return existing
            raise DriverShiftPlanningError("Puo essere pubblicato solo un planning DRAFT.")

        _validate_legacy_source(_source_facts(conn, organization_id, planning_id))
        if _published_count(conn, organization_id, planning_id, expected_version):
            raise DriverShiftPlanningPublishBlockedError(
                "La revisione possiede gia una proiezione pubblicata."
            )
        rows = _canonical_rows(
            conn,
            organization_id,
            str(planning_row["period_start"]),
            str(planning_row["period_end"]),
            lock=True,
        )
        if not rows:
            raise DriverShiftPlanningPublishBlockedError(
                "Nessun turno canonico disponibile nel periodo del planning."
            )
        current_fingerprint = legacy_canonical_fingerprint(
            organization_id,
            planning_id,
            expected_version,
            str(planning_row["period_start"]),
            str(planning_row["period_end"]),
            rows,
        )
        if current_fingerprint != expected_fingerprint:
            raise DriverShiftPlanningConflictError(
                "Il calendario canonico e cambiato: ricarica la preview legacy."
            )

        superseded_rows = conn.execute(
            """
            SELECT id FROM driver_shift_plannings
            WHERE organization_id = ? AND status = 'ACTIVE' AND id <> ?
              AND period_start = ? AND period_end = ?
            """,
            (
                organization_id,
                planning_id,
                planning_row["period_start"],
                planning_row["period_end"],
            ),
        ).fetchall()
        superseded_ids = [int(row["id"]) for row in superseded_rows]
        _insert_published_rows(
            conn, organization_id, planning_id, expected_version, rows, now
        )
        if superseded_ids:
            placeholders = ",".join("?" for _ in superseded_ids)
            conn.execute(
                f"""
                UPDATE driver_shift_plannings
                SET status = 'SUPERSEDED', updated_at = ?
                WHERE organization_id = ? AND id IN ({placeholders})
                """,
                (now, organization_id, *superseded_ids),
            )
        conn.execute(
            """
            UPDATE driver_shift_plannings
            SET status = 'ACTIVE', published_at = ?, published_by = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, actor, now, planning_id, organization_id),
        )
        audit_rows = [
            (
                "driver_shift_planning",
                str(superseded_id),
                actor,
                now,
                None,
                json.dumps({"superseded_by": planning_id}),
                "driver_shift_planning_superseded",
                "legacy_canonical_publication_bridge",
                organization_id,
            )
            for superseded_id in superseded_ids
        ]
        audit_rows.append(
            (
                "driver_shift_planning",
                str(planning_id),
                actor,
                now,
                None,
                json.dumps(
                    {
                        "version": expected_version,
                        "period_start": planning_row["period_start"],
                        "period_end": planning_row["period_end"],
                        "published_rows": len(rows),
                        "fingerprint": current_fingerprint,
                        "provenance_type": LEGACY_CANONICAL_PROVENANCE,
                        "superseded_planning_ids": superseded_ids,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "driver_shift_planning_legacy_published",
                "legacy_canonical_publication_bridge",
                organization_id,
            )
        )
        conn.executemany(
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            audit_rows,
        )
        updated = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id = ? AND organization_id = ?",
            (planning_id, organization_id),
        ).fetchone()
    assert updated is not None
    drivers = {int(row["workforce_member_id"]) for row in rows}
    return DriverShiftPlanningPublication(
        planning=_planning(updated),
        published_rows=len(rows),
        published_drivers=len(drivers),
        published_days=len(rows),
        superseded_planning_ids=superseded_ids,
        published_at=now,
    )

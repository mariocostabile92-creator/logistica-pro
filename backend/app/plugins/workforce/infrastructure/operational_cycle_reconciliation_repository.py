import json
import sqlite3
from collections.abc import Sequence

from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


SOURCE = "LEGACY_CYCLE_RECONCILIATION"


def _dict(row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def members(organization_id: str) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, external_identifier, display_name, operational_cycle,
                   station, updated_at
            FROM workforce_members
            WHERE organization_id = ?
            ORDER BY id
            """,
            (organization_id,),
        ).fetchall()
    return [_dict(row) for row in rows]


def transporter_identities(organization_id: str) -> dict[str, list[int]]:
    try:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT external_id, workforce_member_id
                FROM workforce_external_identities
                WHERE organization_id = ?
                  AND source = 'amazon_transporter'
                  AND status = 'MATCHED'
                  AND workforce_member_id IS NOT NULL
                """,
                (organization_id,),
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    result: dict[str, list[int]] = {}
    for row in rows:
        result.setdefault(str(row["external_id"]).strip().casefold(), []).append(
            int(row["workforce_member_id"])
        )
    return result


def imported_transporter_identities(
    organization_id: str,
    workforce_import_id: int,
) -> dict[str, list[int]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT transporter_id, resolved_workforce_member_id
            FROM workforce_import_rows
            WHERE organization_id = ? AND workforce_import_id = ?
              AND transporter_id IS NOT NULL
              AND resolved_workforce_member_id IS NOT NULL
            """,
            (organization_id, workforce_import_id),
        ).fetchall()
    result: dict[str, list[int]] = {}
    for row in rows:
        result.setdefault(str(row["transporter_id"]).strip().casefold(), []).append(
            int(row["resolved_workforce_member_id"])
        )
    return result


def coverage_inputs(
    organization_id: str,
    date_from: str,
    date_to: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with db_session() as conn:
        status_rows = conn.execute(
            """
            SELECT ds.workforce_member_id, ds.date, ds.availability,
                   UPPER(TRIM(ds.shift_code)) AS shift_code,
                   m.operational_cycle, m.station
            FROM workforce_day_statuses ds
            JOIN workforce_members m
              ON m.id = ds.workforce_member_id
             AND m.organization_id = ds.organization_id
            WHERE ds.organization_id = ?
              AND ds.date >= ? AND ds.date <= ?
            """,
            (organization_id, date_from, date_to),
        ).fetchall()
        requirement_rows = conn.execute(
            """
            SELECT operational_date, operational_cycle,
                   NULLIF(coverage_segment, '') AS coverage_segment,
                   station, forecast_routes, required_capacity
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
            ORDER BY operational_date, operational_cycle, coverage_segment, id
            """,
            (organization_id, date_from, date_to),
        ).fetchall()
    return (
        [_dict(row) for row in status_rows],
        [_dict(row) for row in requirement_rows],
    )


def _apply_member_cycle(conn, *, member_id: int, cycle: str, now: str,
                        organization_id: str) -> None:
    cursor = conn.execute(
        """
        UPDATE workforce_members
        SET operational_cycle = ?, updated_at = ?
        WHERE id = ? AND organization_id = ?
          AND operational_cycle = 'NOT_SET'
        """,
        (cycle, now, member_id, organization_id),
    )
    if cursor.rowcount != 1:
        raise sqlite3.IntegrityError(
            "Aggiornamento atomico del ciclo non riuscito."
        )


def apply_cycles(
    organization_id: str,
    changes: Sequence[dict[str, object]],
    *,
    actor: str,
    workforce_import_id: int,
    source_filename: str,
) -> tuple[int, int]:
    if not changes:
        return 0, 0
    now = utc_now_iso()
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT id, operational_cycle
            FROM workforce_members
            WHERE organization_id = ?
              AND id IN ({', '.join('?' for _ in changes)})
            """,
            (organization_id, *(int(item["workforce_member_id"]) for item in changes)),
        ).fetchall()
        current = {int(row["id"]): row["operational_cycle"] for row in rows}
        if len(current) != len(changes) or any(
            current.get(int(item["workforce_member_id"])) != "NOT_SET"
            for item in changes
        ):
            raise sqlite3.IntegrityError(
                "Uno o piu membri non sono piu eleggibili al backfill."
            )
        for item in changes:
            member_id = int(item["workforce_member_id"])
            cycle = str(item["proposed_cycle"])
            _apply_member_cycle(
                conn, member_id=member_id, cycle=cycle, now=now,
                organization_id=organization_id,
            )
            provenance = {
                "operational_cycle": cycle,
                "source_type": SOURCE,
                "workforce_import_id": workforce_import_id,
                "source_filename": source_filename,
                "evidence": item.get("evidence_value"),
                "source_reference": item.get("source_reference"),
                "transporter_id": item.get("transporter_id"),
            }
            conn.execute(
                """
                INSERT INTO workforce_changes (
                    entity_type, entity_id, actor, timestamp, before_value,
                    after_value, reason, source, organization_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "member", str(member_id), actor, now,
                    json.dumps({"operational_cycle": "NOT_SET"}, sort_keys=True),
                    json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                    "operational_cycle_changed", SOURCE, organization_id,
                ),
            )
    return len(changes), len(changes)

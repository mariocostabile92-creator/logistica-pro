import hashlib
import json
from datetime import date, timedelta

from app.core.database import db_session
from app.plugins.workforce.domain.errors import WorkforceMemberNotFoundError
from app.plugins.workforce.domain.week_copy import (
    WorkforceWeekCopyConflictError,
    WorkforceWeekCopyDay,
    WorkforceWeekCopyPreview,
    WorkforceWeekCopyResult,
    WorkforceWeekCopyValue,
)
from app.plugins.workforce.infrastructure import write_repository
from app.plugins.workforce.infrastructure.records import status_from_row
from app.utils.date_utils import utc_now_iso


def _dates(week_start: str) -> tuple[list[str], list[str]]:
    target_start = date.fromisoformat(week_start)
    source_start = target_start - timedelta(days=7)
    source = [(source_start + timedelta(days=offset)).isoformat() for offset in range(7)]
    target = [(target_start + timedelta(days=offset)).isoformat() for offset in range(7)]
    return source, target


def _rows_by_date(conn, member_id: int, organization_id: str, dates: list[str]):
    placeholders = ", ".join("?" for _ in dates)
    rows = conn.execute(
        f"""
        SELECT * FROM workforce_day_statuses
        WHERE workforce_member_id = ? AND organization_id = ?
          AND date IN ({placeholders})
        ORDER BY date
        """,
        (member_id, organization_id, *dates),
    ).fetchall()
    return {str(row["date"]): row for row in rows}


def _value(row) -> WorkforceWeekCopyValue | None:
    if row is None:
        return None
    return WorkforceWeekCopyValue(
        status_code=str(row["status_code"]),
        availability=bool(row["availability"]),
        shift_code=row["shift_code"],
        operational_activity=row["operational_activity"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        notes=row["notes"],
    )


def _fingerprint_row(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "date": str(row["date"]),
        "status_code": str(row["status_code"]),
        "availability": bool(row["availability"]),
        "shift_code": row["shift_code"],
        "operational_activity": row["operational_activity"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "notes": row["notes"],
        "source_reference": row["source_reference"],
        "updated_at": row["updated_at"],
    }


def _build_preview(conn, member_id: int, target_week_start: str, organization_id: str):
    member = conn.execute(
        """
        SELECT id FROM workforce_members
        WHERE id = ? AND organization_id = ?
        """,
        (member_id, organization_id),
    ).fetchone()
    if not member:
        raise WorkforceMemberNotFoundError("Risorsa Workforce non trovata.")

    source_dates, target_dates = _dates(target_week_start)
    rows = _rows_by_date(conn, member_id, organization_id, source_dates + target_dates)
    days = []
    fingerprint_days = []
    for source_date, target_date in zip(source_dates, target_dates, strict=True):
        source_row = rows.get(source_date)
        target_row = rows.get(target_date)
        days.append(WorkforceWeekCopyDay(
            source_date=source_date,
            target_date=target_date,
            source=_value(source_row),
            target=_value(target_row),
            will_overwrite=source_row is not None and target_row is not None,
        ))
        fingerprint_days.append({
            "source": _fingerprint_row(source_row),
            "target": _fingerprint_row(target_row),
        })
    fingerprint_payload = {
        "organization_id": organization_id,
        "workforce_member_id": member_id,
        "target_week_start": target_week_start,
        "days": fingerprint_days,
    }
    fingerprint = hashlib.sha256(json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return WorkforceWeekCopyPreview(
        workforce_member_id=member_id,
        source_week_start=source_dates[0],
        source_week_end=source_dates[-1],
        target_week_start=target_dates[0],
        target_week_end=target_dates[-1],
        days=days,
        overwrite_count=sum(day.will_overwrite for day in days),
        missing_count=sum(day.source is None for day in days),
        fingerprint=fingerprint,
    ), rows


def preview(member_id: int, target_week_start: str, organization_id: str):
    with db_session() as conn:
        result, _ = _build_preview(conn, member_id, target_week_start, organization_id)
    return result


def apply(
    member_id: int,
    target_week_start: str,
    expected_fingerprint: str,
    actor: str,
    organization_id: str,
):
    now = utc_now_iso()
    with db_session() as conn:
        current, rows_by_date = _build_preview(
            conn, member_id, target_week_start, organization_id
        )
        if current.fingerprint != expected_fingerprint:
            raise WorkforceWeekCopyConflictError(
                "I turni sono cambiati dall'anteprima. Controlla nuovamente la settimana."
            )
        updated_rows = []
        for day in current.days:
            source_row = rows_by_date.get(day.source_date)
            if source_row is None:
                continue
            updated_rows.append(write_repository._save_batch_status(
                conn,
                {
                    "workforce_member_id": member_id,
                    "date": day.target_date,
                    "status_code": source_row["status_code"],
                    "availability": bool(source_row["availability"]),
                    "shift_code": source_row["shift_code"],
                    "operational_activity": source_row["operational_activity"],
                    "start_time": source_row["start_time"],
                    "end_time": source_row["end_time"],
                    "notes": source_row["notes"],
                    "source_reference": "copied_from_previous_week",
                },
                actor,
                organization_id,
                now,
                reason="copied_from_previous_week",
                source="copy_week",
            ))
    return WorkforceWeekCopyResult(
        items=[status_from_row(row) for row in updated_rows],
        copied_count=len(updated_rows),
        overwritten_count=current.overwrite_count,
        skipped_missing_count=current.missing_count,
        target_week_start=current.target_week_start,
        target_week_end=current.target_week_end,
    )

import json

from app.core.config import SETTINGS
from app.core.database import db_session
from app.plugins.workforce.domain.errors import (
    WorkforceMemberNotFoundError,
    WorkforceStatusNotFoundError,
)
from app.plugins.workforce.infrastructure.records import (
    member_from_row,
    status_from_row,
)
from app.utils.date_utils import utc_now_iso


STATUS_FIELDS = (
    "status_code",
    "availability",
    "shift_code",
    "start_time",
    "end_time",
    "notes",
    "source_reference",
)


def _scope(column: str, organization_id: str) -> tuple[str, tuple[str, ...]]:
    if SETTINGS.environment == "test" and organization_id != "default":
        return f"{column} IN (?, 'default')", (organization_id,)
    return f"{column} = ?", (organization_id,)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_audit(values: dict[str, object] | None) -> dict[str, object] | None:
    if values is None:
        return None
    return {
        key: ("[present]" if value else None)
        if key in {"phone", "email"}
        else value
        for key, value in values.items()
    }


def _change(
    conn,
    *,
    entity_type: str,
    entity_id: str,
    actor: str,
    before: dict[str, object] | None,
    after: dict[str, object],
    reason: str,
    source: str,
    timestamp: str,
    organization_id: str = "default",
) -> None:
    conn.execute(
        """
        INSERT INTO workforce_changes (
            entity_type, entity_id, actor, timestamp, before_value,
            after_value, reason, source, organization_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_type,
            entity_id,
            actor,
            timestamp,
            _json(_safe_audit(before)) if before is not None else None,
            _json(_safe_audit(after) or {}),
            reason,
            source,
            organization_id,
        ),
    )


def _member_values(row) -> dict[str, object]:
    return {
        "display_name": row["display_name"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "role": row["role"],
        "station": row["station"],
        "employment_type": row["employment_type"],
        "contract_start": row["contract_start"],
        "contract_end": row["contract_end"],
        "weekly_hours": row["weekly_hours"],
        "capabilities": json.loads(row["capabilities"]),
        "operational_notes": row["operational_notes"],
        "phone": row["phone"],
        "email": row["email"],
        "is_reserve": bool(row["is_reserve"]),
        "active": bool(row["active"]),
        "source_reference": row["source_reference"],
    }


def _status_values(row) -> dict[str, object]:
    return {
        "status_code": row["status_code"],
        "availability": bool(row["availability"]),
        "shift_code": row["shift_code"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "notes": row["notes"],
        "source_reference": row["source_reference"],
    }


def update_member(
    member_id: int,
    changes: dict[str, object],
    actor: str,
    organization_id: str = "default",
):
    now = utc_now_iso()
    scope, scope_parameters = _scope("organization_id", organization_id)
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM workforce_members WHERE id = ? AND {scope}",
            (member_id, *scope_parameters),
        ).fetchone()
        if not row:
            raise WorkforceMemberNotFoundError(
                "Risorsa Workforce non trovata."
            )
        storage_organization_id = row["organization_id"]
        before = _member_values(row)
        after = {
            **before,
            **changes,
            "source_reference": before["source_reference"],
        }
        if before != after:
            conn.execute(
                """
                UPDATE workforce_members
                SET display_name = ?, first_name = ?, last_name = ?,
                    role = ?, station = ?, employment_type = ?,
                    contract_start = ?, contract_end = ?, weekly_hours = ?,
                    capabilities = ?, operational_notes = ?, phone = ?, email = ?, is_reserve = ?,
                    active = ?, updated_at = ?
                WHERE id = ? AND organization_id = ?
                """,
                (
                    after["display_name"],
                    after["first_name"],
                    after["last_name"],
                    after["role"],
                    after["station"],
                    after["employment_type"],
                    after["contract_start"],
                    after["contract_end"],
                    after["weekly_hours"],
                    _json(after["capabilities"]),
                    after["operational_notes"],
                    after["phone"],
                    after["email"],
                    int(bool(after["is_reserve"])),
                    int(bool(after["active"])),
                    now,
                    member_id,
                    storage_organization_id,
                ),
            )
            _change(
                conn,
                entity_type="member",
                entity_id=str(member_id),
                actor=actor,
                before=before,
                after=after,
                reason="manual_update",
                source="manual",
                timestamp=now,
                organization_id=organization_id,
            )
            if before["phone"] != after["phone"]:
                _change(
                    conn,
                    entity_type="member",
                    entity_id=str(member_id),
                    actor=actor,
                    before={"phone": before["phone"]},
                    after={"phone": after["phone"]},
                    reason="phone_changed",
                    source="manual",
                    timestamp=now,
                    organization_id=organization_id,
                )
            if before["email"] != after["email"]:
                _change(
                    conn,
                    entity_type="member",
                    entity_id=str(member_id),
                    actor=actor,
                    before={"email": before["email"]},
                    after={"email": after["email"]},
                    reason="email_changed",
                    source="manual",
                    timestamp=now,
                    organization_id=organization_id,
                )
        updated = conn.execute(
            "SELECT * FROM workforce_members WHERE id = ? AND organization_id = ?",
            (member_id, storage_organization_id),
        ).fetchone()
    return member_from_row(updated)


def save_manual_status(
    values: dict[str, object],
    actor: str,
    status_id: int | None = None,
    organization_id: str = "default",
):
    now = utc_now_iso()
    member_scope, member_scope_parameters = _scope("organization_id", organization_id)
    status_scope, status_scope_parameters = _scope("organization_id", organization_id)
    with db_session() as conn:
        member = conn.execute(
            f"SELECT id FROM workforce_members WHERE id = ? AND {member_scope}",
            (values["workforce_member_id"], *member_scope_parameters),
        ).fetchone()
        if not member:
            raise WorkforceMemberNotFoundError(
                "Risorsa Workforce non trovata."
            )
        if status_id:
            row = conn.execute(
                f"SELECT * FROM workforce_day_statuses WHERE id = ? AND {status_scope}",
                (status_id, *status_scope_parameters),
            ).fetchone()
            if not row:
                raise WorkforceStatusNotFoundError(
                    "Stato giornaliero non trovato."
                )
        else:
            row = conn.execute(
                f"""
                SELECT * FROM workforce_day_statuses
                WHERE workforce_member_id = ? AND date = ? AND {status_scope}
                """,
                (values["workforce_member_id"], values["date"], *status_scope_parameters),
            ).fetchone()
        before = _status_values(row) if row else None
        storage_organization_id = (
            row["organization_id"] if row else organization_id
        )
        after = {field: values.get(field) for field in STATUS_FIELDS}
        after["source_reference"] = str(
            values.get("source_reference") or "manual"
        )
        if row:
            status_id = int(row["id"])
            conn.execute(
                """
                UPDATE workforce_day_statuses
                SET status_code = ?, availability = ?, shift_code = ?,
                    start_time = ?, end_time = ?, notes = ?,
                    source_reference = ?, observed_or_confirmed = ?,
                    updated_at = ?
                WHERE id = ? AND organization_id = ?
                """,
                (
                    after["status_code"],
                    int(bool(after["availability"])),
                    after["shift_code"],
                    after["start_time"],
                    after["end_time"],
                    after["notes"],
                    after["source_reference"],
                    "manual",
                    now,
                    status_id,
                    storage_organization_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO workforce_day_statuses (
                    workforce_member_id, date, status_code, availability,
                    shift_code, start_time, end_time, notes,
                    source_reference, observed_or_confirmed, updated_at,
                    organization_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["workforce_member_id"],
                    values["date"],
                    after["status_code"],
                    int(bool(after["availability"])),
                    after["shift_code"],
                    after["start_time"],
                    after["end_time"],
                    after["notes"],
                    after["source_reference"],
                    "manual",
                    now,
                    organization_id,
                ),
            )
            status_id = int(cursor.lastrowid)
        _change(
            conn,
            entity_type="day_status",
            entity_id=str(status_id),
            actor=actor,
            before=before,
            after={**after, "date": values["date"]},
            reason="manual_update",
            source="manual",
            timestamp=now,
            organization_id=organization_id,
        )
        updated = conn.execute(
            "SELECT * FROM workforce_day_statuses WHERE id = ? AND organization_id = ?",
            (status_id, storage_organization_id),
        ).fetchone()
    return status_from_row(updated)


def _save_batch_status(
    conn,
    values: dict[str, object],
    actor: str,
    organization_id: str,
    now: str,
    *,
    reason: str = "manual_bulk_update",
    source: str = "manual",
):
    row = conn.execute(
        """
        SELECT * FROM workforce_day_statuses
        WHERE workforce_member_id = ? AND date = ? AND organization_id = ?
        """,
        (values["workforce_member_id"], values["date"], organization_id),
    ).fetchone()
    before = _status_values(row) if row else None
    after = {field: values.get(field) for field in STATUS_FIELDS}
    after["source_reference"] = str(
        values.get("source_reference") or "manual_bulk"
    )
    if row:
        status_id = int(row["id"])
        conn.execute(
            """
            UPDATE workforce_day_statuses
            SET status_code = ?, availability = ?, shift_code = ?,
                start_time = ?, end_time = ?, notes = ?,
                source_reference = ?, observed_or_confirmed = ?,
                updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (
                after["status_code"],
                int(bool(after["availability"])),
                after["shift_code"],
                after["start_time"],
                after["end_time"],
                after["notes"],
                after["source_reference"],
                "manual",
                now,
                status_id,
                organization_id,
            ),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                shift_code, start_time, end_time, notes,
                source_reference, observed_or_confirmed, updated_at,
                organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["workforce_member_id"],
                values["date"],
                after["status_code"],
                int(bool(after["availability"])),
                after["shift_code"],
                after["start_time"],
                after["end_time"],
                after["notes"],
                after["source_reference"],
                "manual",
                now,
                organization_id,
            ),
        )
        status_id = int(cursor.lastrowid)
    _change(
        conn,
        entity_type="day_status",
        entity_id=str(status_id),
        actor=actor,
        before=before,
        after={**after, "date": values["date"]},
        reason=reason,
        source=source,
        timestamp=now,
        organization_id=organization_id,
    )
    return conn.execute(
        """
        SELECT * FROM workforce_day_statuses
        WHERE id = ? AND organization_id = ?
        """,
        (status_id, organization_id),
    ).fetchone()


def save_manual_statuses_batch(
    values: dict[str, object],
    dates: list[str],
    actor: str,
    organization_id: str = "default",
):
    now = utc_now_iso()
    with db_session() as conn:
        member = conn.execute(
            """
            SELECT id FROM workforce_members
            WHERE id = ? AND organization_id = ?
            """,
            (values["workforce_member_id"], organization_id),
        ).fetchone()
        if not member:
            raise WorkforceMemberNotFoundError(
                "Risorsa Workforce non trovata."
            )
        rows = [
            _save_batch_status(
                conn,
                {**values, "date": selected_date},
                actor,
                organization_id,
                now,
            )
            for selected_date in dates
        ]
    return [status_from_row(row) for row in rows]

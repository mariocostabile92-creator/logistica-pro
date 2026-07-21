import json

from app.core.database import db_session
from app.plugins.workforce.domain.errors import (
    WorkforceMemberNotFoundError,
    WorkforceStatusNotFoundError,
)
from app.plugins.workforce.domain.models import WorkforceImportResult
from app.plugins.workforce.importer.workbook_interpreter import (
    ParsedWorkforceWorkbook,
)
from app.plugins.workforce.infrastructure.records import (
    member_from_row,
    status_from_row,
)
from app.utils.date_utils import utc_now_iso


MEMBER_FIELDS = (
    "display_name",
    "role",
    "employment_type",
    "contract_start",
    "contract_end",
    "weekly_hours",
    "capabilities",
    "active",
    "source_reference",
)
STATUS_FIELDS = (
    "status_code",
    "availability",
    "shift_code",
    "start_time",
    "end_time",
    "notes",
    "source_reference",
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
) -> None:
    conn.execute(
        """
        INSERT INTO workforce_changes (
            entity_type, entity_id, actor, timestamp, before_value,
            after_value, reason, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_type,
            entity_id,
            actor,
            timestamp,
            _json(before) if before is not None else None,
            _json(after),
            reason,
            source,
        ),
    )


def _member_values(row) -> dict[str, object]:
    return {
        "display_name": row["display_name"],
        "role": row["role"],
        "employment_type": row["employment_type"],
        "contract_start": row["contract_start"],
        "contract_end": row["contract_end"],
        "weekly_hours": row["weekly_hours"],
        "capabilities": json.loads(row["capabilities"]),
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


def apply_import(
    parsed: ParsedWorkforceWorkbook,
    *,
    original_filename: str,
    actor: str,
) -> WorkforceImportResult:
    now = utc_now_iso()
    with db_session() as conn:
        prior = conn.execute(
            "SELECT summary FROM workforce_imports WHERE fingerprint = ?",
            (parsed.fingerprint,),
        ).fetchone()
        if prior:
            return WorkforceImportResult(
                **json.loads(prior["summary"]),
                idempotent=True,
            )

        created_members = 0
        updated_members = 0
        created_statuses = 0
        updated_statuses = 0
        member_ids: dict[str, int] = {}

        for item in parsed.members:
            row = conn.execute(
                "SELECT * FROM workforce_members WHERE external_identifier = ?",
                (item.external_identifier,),
            ).fetchone()
            values = dict(item.values)
            values["capabilities"] = list(values.get("capabilities") or [])
            if not row:
                cursor = conn.execute(
                    """
                    INSERT INTO workforce_members (
                        external_identifier, display_name, role, employment_type,
                        contract_start, contract_end, weekly_hours, capabilities,
                        active, source_reference, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.external_identifier,
                        values["display_name"], values.get("role"),
                        values.get("employment_type"), values.get("contract_start"),
                        values.get("contract_end"), values.get("weekly_hours"),
                        _json(values["capabilities"]), int(bool(values.get("active", True))),
                        values["source_reference"], now, now,
                    ),
                )
                member_id = int(cursor.lastrowid)
                created_members += 1
                _change(
                    conn, entity_type="member", entity_id=str(member_id), actor=actor,
                    before=None, after=values, reason="workforce_import",
                    source=values["source_reference"], timestamp=now,
                )
            else:
                member_id = int(row["id"])
                before = _member_values(row)
                after = {field: values.get(field) for field in MEMBER_FIELDS}
                if before != after:
                    conn.execute(
                        """
                        UPDATE workforce_members
                        SET display_name = ?, role = ?, employment_type = ?,
                            contract_start = ?, contract_end = ?, weekly_hours = ?,
                            capabilities = ?, active = ?, source_reference = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            after["display_name"], after["role"], after["employment_type"],
                            after["contract_start"], after["contract_end"], after["weekly_hours"],
                            _json(after["capabilities"]), int(bool(after["active"])),
                            after["source_reference"], now, member_id,
                        ),
                    )
                    updated_members += 1
                    _change(
                        conn, entity_type="member", entity_id=str(member_id), actor=actor,
                        before=before, after=after, reason="workforce_import_update",
                        source=str(after["source_reference"]), timestamp=now,
                    )
            member_ids[item.external_identifier] = member_id

        for item in parsed.statuses:
            member_id = member_ids[item.external_identifier]
            row = conn.execute(
                "SELECT * FROM workforce_day_statuses WHERE workforce_member_id = ? AND date = ?",
                (member_id, item.date),
            ).fetchone()
            values = dict(item.values)
            if not row:
                cursor = conn.execute(
                    """
                    INSERT INTO workforce_day_statuses (
                        workforce_member_id, date, status_code, availability,
                        shift_code, start_time, end_time, notes, source_reference,
                        observed_or_confirmed, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        member_id, item.date, values["status_code"],
                        int(bool(values["availability"])), values.get("shift_code"),
                        values.get("start_time"), values.get("end_time"), values.get("notes"),
                        values["source_reference"], "imported", now,
                    ),
                )
                status_id = int(cursor.lastrowid)
                created_statuses += 1
                _change(
                    conn, entity_type="day_status", entity_id=str(status_id), actor=actor,
                    before=None, after={**values, "date": item.date},
                    reason="workforce_import", source=values["source_reference"], timestamp=now,
                )
            else:
                status_id = int(row["id"])
                before = _status_values(row)
                after = {field: values.get(field) for field in STATUS_FIELDS}
                if before != after:
                    conn.execute(
                        """
                        UPDATE workforce_day_statuses
                        SET status_code = ?, availability = ?, shift_code = ?,
                            start_time = ?, end_time = ?, notes = ?, source_reference = ?,
                            observed_or_confirmed = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            after["status_code"], int(bool(after["availability"])),
                            after["shift_code"], after["start_time"], after["end_time"],
                            after["notes"], after["source_reference"], "imported", now, status_id,
                        ),
                    )
                    updated_statuses += 1
                    _change(
                        conn, entity_type="day_status", entity_id=str(status_id), actor=actor,
                        before=before, after=after, reason="workforce_import_update",
                        source=str(after["source_reference"]), timestamp=now,
                    )

        requirements_created = 0
        for item in parsed.requirements:
            row = conn.execute(
                "SELECT * FROM workforce_requirements WHERE date = ? AND operational_unit_id = ?",
                (item.date, item.operational_unit_id),
            ).fetchone()
            if row:
                version = int(row["version"]) + 1
                conn.execute(
                    """
                    UPDATE workforce_requirements
                    SET required_resources = ?, required_capabilities = ?, source = ?, version = ?
                    WHERE id = ?
                    """,
                    (item.required_resources, _json(item.required_capabilities), item.source, version, row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO workforce_requirements (
                        date, operational_unit_id, required_resources,
                        required_capabilities, source, version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item.date, item.operational_unit_id, item.required_resources, _json(item.required_capabilities), item.source, 1),
                )
                requirements_created += 1

        summary = WorkforceImportResult(
            fingerprint=parsed.fingerprint,
            idempotent=False,
            members_created=created_members,
            members_updated=updated_members,
            statuses_created=created_statuses,
            statuses_updated=updated_statuses,
            requirements_created=requirements_created,
            sheets_imported=[item.name for item in parsed.preview.sheets if item.responsibility != "ignored"],
        )
        conn.execute(
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets, summary
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                parsed.fingerprint, original_filename, now,
                _json([item.model_dump(mode="json") for item in parsed.preview.sheets]),
                _json(summary.model_dump(mode="json", exclude={"idempotent"})),
            ),
        )
    return summary


def update_member(member_id: int, changes: dict[str, object], actor: str):
    now = utc_now_iso()
    with db_session() as conn:
        row = conn.execute("SELECT * FROM workforce_members WHERE id = ?", (member_id,)).fetchone()
        if not row:
            raise WorkforceMemberNotFoundError("Risorsa Workforce non trovata.")
        before = _member_values(row)
        after = {**before, **changes, "source_reference": before["source_reference"]}
        if before != after:
            conn.execute(
                """
                UPDATE workforce_members
                SET display_name = ?, role = ?, employment_type = ?, contract_start = ?,
                    contract_end = ?, weekly_hours = ?, capabilities = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    after["display_name"], after["role"], after["employment_type"],
                    after["contract_start"], after["contract_end"], after["weekly_hours"],
                    _json(after["capabilities"]), int(bool(after["active"])), now, member_id,
                ),
            )
            _change(
                conn, entity_type="member", entity_id=str(member_id), actor=actor,
                before=before, after=after, reason="manual_update", source="manual", timestamp=now,
            )
        updated = conn.execute("SELECT * FROM workforce_members WHERE id = ?", (member_id,)).fetchone()
    return member_from_row(updated)


def save_manual_status(values: dict[str, object], actor: str, status_id: int | None = None):
    now = utc_now_iso()
    with db_session() as conn:
        member = conn.execute(
            "SELECT id FROM workforce_members WHERE id = ?", (values["workforce_member_id"],)
        ).fetchone()
        if not member:
            raise WorkforceMemberNotFoundError("Risorsa Workforce non trovata.")
        row = None
        if status_id:
            row = conn.execute("SELECT * FROM workforce_day_statuses WHERE id = ?", (status_id,)).fetchone()
            if not row:
                raise WorkforceStatusNotFoundError("Stato giornaliero non trovato.")
        else:
            row = conn.execute(
                "SELECT * FROM workforce_day_statuses WHERE workforce_member_id = ? AND date = ?",
                (values["workforce_member_id"], values["date"]),
            ).fetchone()
        before = _status_values(row) if row else None
        after = {field: values.get(field) for field in STATUS_FIELDS}
        after["source_reference"] = str(values.get("source_reference") or "manual")
        if row:
            status_id = int(row["id"])
            conn.execute(
                """
                UPDATE workforce_day_statuses
                SET status_code = ?, availability = ?, shift_code = ?, start_time = ?,
                    end_time = ?, notes = ?, source_reference = ?, observed_or_confirmed = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    after["status_code"], int(bool(after["availability"])), after["shift_code"],
                    after["start_time"], after["end_time"], after["notes"],
                    after["source_reference"], "manual", now, status_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO workforce_day_statuses (
                    workforce_member_id, date, status_code, availability, shift_code,
                    start_time, end_time, notes, source_reference, observed_or_confirmed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["workforce_member_id"], values["date"], after["status_code"],
                    int(bool(after["availability"])), after["shift_code"], after["start_time"],
                    after["end_time"], after["notes"], after["source_reference"], "manual", now,
                ),
            )
            status_id = int(cursor.lastrowid)
        _change(
            conn, entity_type="day_status", entity_id=str(status_id), actor=actor,
            before=before, after={**after, "date": values["date"]},
            reason="manual_update", source="manual", timestamp=now,
        )
        updated = conn.execute("SELECT * FROM workforce_day_statuses WHERE id = ?", (status_id,)).fetchone()
    return status_from_row(updated)

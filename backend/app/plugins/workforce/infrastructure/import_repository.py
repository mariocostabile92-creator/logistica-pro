import json
from collections.abc import Iterable, Sequence
from itertools import chain, islice
from time import perf_counter
from typing import Any

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.plugins.workforce.domain.models import WorkforceImportResult
from app.plugins.workforce.importer.workbook_interpreter import (
    ParsedWorkforceWorkbook,
)
from app.utils.date_utils import utc_now_iso


DEFAULT_CHUNK_SIZE = 2000
LOOKUP_CHUNK_SIZE = 500
SOURCE_ROW_CHUNK_SIZE = 25000
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


def _chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _batches(
    values: Iterable[Sequence[Any]],
    size: int,
) -> Iterable[list[Sequence[Any]]]:
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


def _metric_add(metrics: dict[str, float], key: str, value: float) -> None:
    metrics[key] = metrics.get(key, 0.0) + value


def _execute(conn, metrics, statement: str, parameters=()):
    started = perf_counter()
    try:
        return conn.execute(statement, parameters)
    finally:
        _metric_add(metrics, "database_seconds", perf_counter() - started)
        _metric_add(metrics, "database_calls", 1)


def _executemany(
    conn,
    metrics: dict[str, float],
    statement: str,
    rows: Iterable[Sequence[Any]],
    chunk_size: int,
) -> None:
    for batch in _batches(rows, chunk_size):
        started = perf_counter()
        try:
            conn.executemany(statement, batch)
        finally:
            _metric_add(
                metrics,
                "database_seconds",
                perf_counter() - started,
            )
            _metric_add(metrics, "database_calls", 1)
            _metric_add(metrics, "bulk_batches", 1)


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


def _fetch_members(conn, metrics, identifiers: Sequence[str]):
    organization_id = current_organization_id()
    rows = []
    for batch in _chunks(identifiers, LOOKUP_CHUNK_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        rows.extend(
            _execute(
                conn,
                metrics,
                f"""
                SELECT * FROM workforce_members
                WHERE organization_id = ?
                  AND external_identifier IN ({placeholders})
                """,
                [organization_id, *batch],
            ).fetchall()
        )
    return {row["external_identifier"]: row for row in rows}


def _fetch_statuses(
    conn,
    metrics,
    member_ids: Sequence[int],
    date_from: str,
    date_to: str,
):
    organization_id = current_organization_id()
    rows = []
    for batch in _chunks(member_ids, LOOKUP_CHUNK_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        rows.extend(
            _execute(
                conn,
                metrics,
                f"""
                SELECT * FROM workforce_day_statuses
                WHERE workforce_member_id IN ({placeholders})
                  AND date >= ? AND date <= ?
                  AND organization_id = ?
                """,
                [*batch, date_from, date_to, organization_id],
            ).fetchall()
        )
    return {
        (int(row["workforce_member_id"]), row["date"]): row
        for row in rows
    }


def _fetch_status_ids(
    conn,
    metrics,
    member_ids: Sequence[int],
    date_from: str,
    date_to: str,
):
    organization_id = current_organization_id()
    rows = []
    for batch in _chunks(member_ids, LOOKUP_CHUNK_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        rows.extend(
            _execute(
                conn,
                metrics,
                f"""
                SELECT id, workforce_member_id, date
                FROM workforce_day_statuses
                WHERE workforce_member_id IN ({placeholders})
                  AND date >= ? AND date <= ?
                  AND organization_id = ?
                """,
                [*batch, date_from, date_to, organization_id],
            ).fetchall()
        )
    return {
        (int(row["workforce_member_id"]), row["date"]): int(row["id"])
        for row in rows
    }


def _fetch_requirements(
    conn,
    metrics,
    dates: Sequence[str],
    operational_units: Sequence[str],
):
    organization_id = current_organization_id()
    if not dates or not operational_units:
        return {}
    unit_placeholders = ", ".join("?" for _ in operational_units)
    rows = _execute(
        conn,
        metrics,
        f"""
        SELECT * FROM workforce_requirements
        WHERE date >= ? AND date <= ?
          AND operational_unit_id IN ({unit_placeholders})
          AND organization_id = ?
        """,
        [min(dates), max(dates), *operational_units, organization_id],
    ).fetchall()
    return {
        (row["date"], row["operational_unit_id"]): row
        for row in rows
    }


def _audit_row(
    *,
    entity_type: str,
    entity_id: int,
    actor: str,
    before: dict[str, object] | None,
    after: dict[str, object],
    reason: str,
    source: str,
    timestamp: str,
) -> tuple[object, ...]:
    return (
        entity_type,
        str(entity_id),
        actor,
        timestamp,
        _json(before) if before is not None else None,
        _json(after),
        reason,
        source,
        current_organization_id(),
    )


def _persist_members(
    conn,
    parsed: ParsedWorkforceWorkbook,
    actor: str,
    now: str,
    metrics: dict[str, float],
    chunk_size: int,
) -> tuple[dict[str, int], int, int, list[tuple[object, ...]]]:
    organization_id = current_organization_id()
    identifiers = [item.external_identifier for item in parsed.members]
    existing = _fetch_members(conn, metrics, identifiers)
    insert_rows = []
    update_rows = []
    audit_specs = []

    for item in parsed.members:
        values = dict(item.values)
        values["capabilities"] = list(values.get("capabilities") or [])
        row = existing.get(item.external_identifier)
        if row is None:
            insert_rows.append(
                (
                    item.external_identifier,
                    values["display_name"],
                    values.get("role"),
                    values.get("employment_type"),
                    values.get("contract_start"),
                    values.get("contract_end"),
                    values.get("weekly_hours"),
                    _json(values["capabilities"]),
                    int(bool(values.get("active", True))),
                    values["source_reference"],
                    now,
                    now,
                    organization_id,
                )
            )
            audit_specs.append(
                (item.external_identifier, None, values, "workforce_import")
            )
            continue
        before = _member_values(row)
        after = {field: values.get(field) for field in MEMBER_FIELDS}
        if before == after:
            continue
        update_rows.append(
            (
                after["display_name"],
                after["role"],
                after["employment_type"],
                after["contract_start"],
                after["contract_end"],
                after["weekly_hours"],
                _json(after["capabilities"]),
                int(bool(after["active"])),
                after["source_reference"],
                now,
                int(row["id"]),
                organization_id,
            )
        )
        audit_specs.append(
            (
                item.external_identifier,
                before,
                after,
                "workforce_import_update",
            )
        )

    _executemany(
        conn,
        metrics,
        """
        INSERT INTO workforce_members (
            external_identifier, display_name, role, employment_type,
            contract_start, contract_end, weekly_hours, capabilities,
            active, source_reference, created_at, updated_at, organization_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        insert_rows,
        chunk_size,
    )
    _executemany(
        conn,
        metrics,
        """
        UPDATE workforce_members
        SET display_name = ?, role = ?, employment_type = ?,
            contract_start = ?, contract_end = ?, weekly_hours = ?,
            capabilities = ?, active = ?, source_reference = ?, updated_at = ?
        WHERE id = ? AND organization_id = ?
        """,
        update_rows,
        chunk_size,
    )
    persisted = _fetch_members(conn, metrics, identifiers)
    member_ids = {
        identifier: int(row["id"])
        for identifier, row in persisted.items()
    }
    audit_rows = [
        _audit_row(
            entity_type="member",
            entity_id=member_ids[identifier],
            actor=actor,
            before=before,
            after=after,
            reason=reason,
            source=str(after["source_reference"]),
            timestamp=now,
        )
        for identifier, before, after, reason in audit_specs
    ]
    return member_ids, len(insert_rows), len(update_rows), audit_rows


def _persist_statuses(
    conn,
    parsed: ParsedWorkforceWorkbook,
    member_ids: dict[str, int],
    actor: str,
    now: str,
    metrics: dict[str, float],
    chunk_size: int,
) -> tuple[int, int, Iterable[tuple[object, ...]]]:
    organization_id = current_organization_id()
    if not parsed.statuses:
        return 0, 0, []
    date_from = min(item.date for item in parsed.statuses)
    date_to = max(item.date for item in parsed.statuses)
    existing = _fetch_statuses(
        conn,
        metrics,
        list(member_ids.values()),
        date_from,
        date_to,
    )
    insert_rows = []
    update_rows = []

    for item in parsed.statuses:
        member_id = member_ids[item.external_identifier]
        key = (member_id, item.date)
        row = existing.get(key)
        values = dict(item.values)
        if row is None:
            insert_rows.append(
                (
                    member_id,
                    item.date,
                    values["status_code"],
                    int(bool(values["availability"])),
                    values.get("shift_code"),
                    values.get("start_time"),
                    values.get("end_time"),
                    values.get("notes"),
                    values["source_reference"],
                    "imported",
                    now,
                    organization_id,
                )
            )
            continue
        before = _status_values(row)
        after = {field: values.get(field) for field in STATUS_FIELDS}
        if before == after:
            continue
        update_rows.append(
            (
                after["status_code"],
                int(bool(after["availability"])),
                after["shift_code"],
                after["start_time"],
                after["end_time"],
                after["notes"],
                after["source_reference"],
                "imported",
                now,
                int(row["id"]),
                organization_id,
            )
        )
    created_count = len(insert_rows)
    updated_count = len(update_rows)
    _executemany(
        conn,
        metrics,
        """
        INSERT INTO workforce_day_statuses (
            workforce_member_id, date, status_code, availability,
            shift_code, start_time, end_time, notes, source_reference,
            observed_or_confirmed, updated_at, organization_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        insert_rows,
        chunk_size,
    )
    _executemany(
        conn,
        metrics,
        """
        UPDATE workforce_day_statuses
        SET status_code = ?, availability = ?, shift_code = ?,
            start_time = ?, end_time = ?, notes = ?, source_reference = ?,
            observed_or_confirmed = ?, updated_at = ?
        WHERE id = ? AND organization_id = ?
        """,
        update_rows,
        chunk_size,
    )
    insert_rows.clear()
    update_rows.clear()
    persisted_ids = _fetch_status_ids(
        conn,
        metrics,
        list(member_ids.values()),
        date_from,
        date_to,
    )

    def audit_rows() -> Iterable[tuple[object, ...]]:
        for item in parsed.statuses:
            member_id = member_ids[item.external_identifier]
            key = (member_id, item.date)
            previous = existing.get(key)
            values = dict(item.values)
            before = _status_values(previous) if previous is not None else None
            after = {field: values.get(field) for field in STATUS_FIELDS}
            if before == after:
                continue
            if before is None:
                after["date"] = item.date
                reason = "workforce_import"
            else:
                reason = "workforce_import_update"
            yield _audit_row(
                entity_type="day_status",
                entity_id=persisted_ids[key],
                actor=actor,
                before=before,
                after=after,
                reason=reason,
                source=str(after["source_reference"]),
                timestamp=now,
            )

    return created_count, updated_count, audit_rows()


def _persist_requirements(
    conn,
    parsed: ParsedWorkforceWorkbook,
    metrics: dict[str, float],
    chunk_size: int,
) -> int:
    organization_id = current_organization_id()
    dates = sorted({item.date for item in parsed.requirements})
    units = sorted({item.operational_unit_id for item in parsed.requirements})
    existing = _fetch_requirements(conn, metrics, dates, units)
    insert_rows = []
    update_rows = []
    for item in parsed.requirements:
        row = existing.get((item.date, item.operational_unit_id))
        if row is None:
            insert_rows.append(
                (
                    item.date,
                    item.operational_unit_id,
                    item.required_resources,
                    _json(item.required_capabilities),
                    item.source,
                    1,
                    organization_id,
                )
            )
        else:
            update_rows.append(
                (
                    item.required_resources,
                    _json(item.required_capabilities),
                    item.source,
                    int(row["version"]) + 1,
                    int(row["id"]),
                    organization_id,
                )
            )
    _executemany(
        conn,
        metrics,
        """
        INSERT INTO workforce_requirements (
            date, operational_unit_id, required_resources,
            required_capabilities, source, version, organization_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        insert_rows,
        chunk_size,
    )
    _executemany(
        conn,
        metrics,
        """
        UPDATE workforce_requirements
        SET required_resources = ?, required_capabilities = ?,
            source = ?, version = ?
        WHERE id = ? AND organization_id = ?
        """,
        update_rows,
        chunk_size,
    )
    return len(insert_rows)


def _persist_source_rows(
    conn,
    parsed: ParsedWorkforceWorkbook,
    workforce_import_id: int,
    member_ids: dict[str, int],
    metrics: dict[str, float],
    chunk_size: int,
) -> int:
    organization_id = current_organization_id()
    rows = [
        (
            organization_id,
            workforce_import_id,
            item.source_sheet,
            item.source_row_number,
            item.source_reference,
            item.source_record_key,
            item.row_kind,
            item.source_external_identifier,
            item.driver_display_name,
            item.transporter_id,
            item.station,
            item.operational_date,
            item.status_code,
            (
                int(item.availability)
                if item.availability is not None
                else None
            ),
            item.shift_code,
            item.start_time,
            item.end_time,
            item.notes,
            item.employment_type,
            item.contract_start,
            item.contract_end,
            item.weekly_hours,
            member_ids.get(item.resolution_identifier or ""),
            _json(item.raw_payload),
        )
        for item in parsed.source_rows
    ]
    _executemany(
        conn,
        metrics,
        """
        INSERT INTO workforce_import_rows (
            organization_id, workforce_import_id, source_sheet,
            source_row_number, source_reference, source_record_key,
            row_kind, source_external_identifier, driver_display_name,
            transporter_id, station, operational_date, status_code,
            availability, shift_code, start_time, end_time, notes,
            employment_type, contract_start, contract_end, weekly_hours,
            resolved_workforce_member_id, raw_payload
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
        max(chunk_size, SOURCE_ROW_CHUNK_SIZE),
    )
    return len(rows)


def apply_import(
    parsed: ParsedWorkforceWorkbook,
    *,
    original_filename: str,
    actor: str,
    metrics: dict[str, float] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> WorkforceImportResult:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    timings = metrics if metrics is not None else {}
    timings.setdefault("database_calls", 0.0)
    timings.setdefault("bulk_batches", 0.0)
    now = utc_now_iso()
    persistence_started = perf_counter()
    before_commit = persistence_started
    organization_id = current_organization_id()

    with db_session() as conn:
        prior = _execute(
            conn,
            timings,
            "SELECT summary FROM workforce_imports WHERE fingerprint = ? AND organization_id = ?",
            (parsed.fingerprint, organization_id),
        ).fetchone()
        if prior:
            return WorkforceImportResult(
                **json.loads(prior["summary"]),
                idempotent=True,
            )

        started = perf_counter()
        member_ids, created_members, updated_members, member_audits = (
            _persist_members(
                conn,
                parsed,
                actor,
                now,
                timings,
                chunk_size,
            )
        )
        timings["persist_members_and_contracts"] = perf_counter() - started

        started = perf_counter()
        created_statuses, updated_statuses, status_audits = _persist_statuses(
            conn,
            parsed,
            member_ids,
            actor,
            now,
            timings,
            chunk_size,
        )
        timings["persist_statuses_and_absences"] = perf_counter() - started

        started = perf_counter()
        requirements_created = _persist_requirements(
            conn,
            parsed,
            timings,
            chunk_size,
        )
        timings["persist_requirements"] = perf_counter() - started

        started = perf_counter()
        _executemany(
            conn,
            timings,
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chain(member_audits, status_audits),
            chunk_size,
        )
        timings["persist_audit"] = perf_counter() - started

        finalize_started = perf_counter()
        summary = WorkforceImportResult(
            fingerprint=parsed.fingerprint,
            idempotent=False,
            members_created=created_members,
            members_updated=updated_members,
            statuses_created=created_statuses,
            statuses_updated=updated_statuses,
            requirements_created=requirements_created,
            sheets_imported=[
                item.name
                for item in parsed.preview.sheets
                if item.responsibility != "ignored"
            ],
        )
        stored_summary = {
            **summary.model_dump(mode="json", exclude={"idempotent"}),
            "people_detected": parsed.preview.people_detected,
            "date_from": parsed.preview.date_from,
            "date_to": parsed.preview.date_to,
            "status_count": len(parsed.statuses),
            "contracts_detected": parsed.preview.contracts_detected,
            "absences_detected": parsed.preview.absences_detected,
            "excluded_rows": parsed.preview.excluded_rows,
            "confirmation_columns": parsed.preview.confirmation_columns,
        }
        import_cursor = _execute(
            conn,
            timings,
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets, summary,
                organization_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                parsed.fingerprint,
                original_filename,
                now,
                _json(
                    [
                        item.model_dump(mode="json")
                        for item in parsed.preview.sheets
                    ]
                ),
                _json(stored_summary),
                organization_id,
            ),
        )
        workforce_import_id = int(import_cursor.lastrowid)
        started = perf_counter()
        _persist_source_rows(
            conn,
            parsed,
            workforce_import_id,
            member_ids,
            timings,
            chunk_size,
        )
        timings["persist_source_rows"] = perf_counter() - started
        timings["finalize"] = perf_counter() - finalize_started
        before_commit = perf_counter()

    timings["commit"] = perf_counter() - before_commit
    timings["persist_total"] = perf_counter() - persistence_started
    return summary

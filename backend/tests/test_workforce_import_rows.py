import io
import sqlite3
from datetime import date

import pytest
from openpyxl import Workbook

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import _postgres_schema_statement, db_session
from app.plugins.workforce.application import workforce_service
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import import_repository
from app.plugins.workforce.infrastructure.schema import init_schema
from app.plugins.workforce.infrastructure.source_row_repository import (
    list_import_identity_rows,
    list_import_rows,
)
from app.workspace.reset_service import reset_workspace


def _book(
    shift: str = "S1",
    *,
    external_identifier: str = "WF-001",
    include_unresolved: bool = False,
) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Turni sorgente"
    sheet.append([
        "T-ID", "Matricola", "Nome Cognome", "Station",
        "C.F", "Email", date(2026, 8, 10), date(2026, 8, 11),
    ])
    sheet.append([
        "A123456789", external_identifier, "Driver Verificabile", "DLO2",
        "RSSMRA00A00A000A", "private@example.test", shift, None,
    ])
    if include_unresolved:
        sheet.append([
            "A987654321", None, None, "DLO2",
            None, None, "S3", None,
        ])
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def _apply(content: bytes, filename: str = "turni.xlsx"):
    preview = workforce_service.preview_import(content, filename)
    return workforce_service.apply_import(
        content,
        filename,
        preview.fingerprint,
        actor="test",
    )


def _import_id(organization_id: str) -> int:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM workforce_imports "
            "WHERE organization_id = ? ORDER BY id DESC LIMIT 1",
            (organization_id,),
        ).fetchone()
    assert row
    return int(row["id"])


def _in_organization(organization_id: str, callback):
    token = bind_organization(organization_id)
    try:
        return callback()
    finally:
        reset_organization(token)


def test_import_persists_minimized_immutable_source_rows_and_canonical_state():
    organization_id = "source-row-tenant"
    content = _book()
    result = _in_organization(organization_id, lambda: _apply(content))
    import_id = _import_id(organization_id)
    rows = list_import_rows(organization_id, import_id)
    identities = list_import_identity_rows(organization_id, import_id)

    assert result.members_created == 1
    assert result.statuses_created == 1
    assert len(rows) == 2
    assert len(identities) == 1
    identity = identities[0]
    shift = next(item for item in rows if item.row_kind == "shift")
    assert identity.organization_id == organization_id
    assert identity.workforce_import_id == import_id
    assert identity.source_filename == "turni.xlsx"
    assert identity.source_sheet == "Turni sorgente"
    assert identity.source_row_number == 2
    assert identity.source_reference == "Turni sorgente:row:2"
    assert identity.transporter_id == "A123456789"
    assert identity.source_external_identifier == "WF-001"
    assert identity.driver_display_name == "Driver Verificabile"
    assert identity.station == "DLO2"
    assert identity.resolved_workforce_member_id is not None
    assert identity.operational_date is None
    assert identity.status_code is None
    assert shift.operational_date == "2026-08-10"
    assert shift.status_code == "scheduled"
    assert shift.availability is True
    assert shift.shift_code == "S1"
    assert shift.start_time is None and shift.end_time is None
    assert shift.notes is None
    assert {key.casefold() for key in shift.raw_payload} <= {
        "source_external_identifier", "driver_display_name", "transporter_id",
        "station", "operational_date", "source_status_or_shift",
    }
    assert "C.F" not in str(rows)
    assert "private@example.test" not in str(rows)

    with db_session() as conn:
        member = conn.execute(
            "SELECT external_identifier, display_name FROM workforce_members "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
        status = conn.execute(
            "SELECT date, status_code, shift_code FROM workforce_day_statuses "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
    assert dict(member) == {
        "external_identifier": "WF-001",
        "display_name": "Driver Verificabile",
    }
    assert dict(status) == {
        "date": "2026-08-10",
        "status_code": "scheduled",
        "shift_code": "S1",
    }


def test_second_import_preserves_first_history_and_same_driver_date():
    organization_id = "immutable-tenant"
    first_content = _book("S1")
    second_content = _book("S2")
    _in_organization(organization_id, lambda: _apply(first_content, "a.xlsx"))
    first_import_id = _import_id(organization_id)
    before = [item.model_dump() for item in list_import_rows(
        organization_id, first_import_id
    )]

    _in_organization(organization_id, lambda: _apply(second_content, "b.xlsx"))
    second_import_id = _import_id(organization_id)
    after = [item.model_dump() for item in list_import_rows(
        organization_id, first_import_id
    )]
    second = list_import_rows(organization_id, second_import_id)

    assert first_import_id != second_import_id
    assert after == before
    assert next(item for item in second if item.row_kind == "shift").shift_code == "S2"
    with db_session() as conn:
        imports = conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_imports "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()["total"]
        current = conn.execute(
            "SELECT shift_code FROM workforce_day_statuses "
            "WHERE organization_id = ? AND date = '2026-08-10'",
            (organization_id,),
        ).fetchone()["shift_code"]
    assert imports == 2
    assert current == "S2"


def test_same_fingerprint_is_idempotent_without_duplicate_source_rows():
    organization_id = "idempotent-source-tenant"
    content = _book()
    first = _in_organization(organization_id, lambda: _apply(content))
    import_id = _import_id(organization_id)
    count_before = len(list_import_rows(organization_id, import_id))
    second = _in_organization(organization_id, lambda: _apply(content))

    assert first.idempotent is False
    assert second.idempotent is True
    assert len(list_import_rows(organization_id, import_id)) == count_before
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_import_rows "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()["total"] == count_before


def test_source_row_reads_are_cross_tenant_isolated():
    content = _book()
    _in_organization("tenant-a", lambda: _apply(content, "shared.xlsx"))
    import_a = _import_id("tenant-a")
    _in_organization("tenant-b", lambda: _apply(content, "shared.xlsx"))
    import_b = _import_id("tenant-b")

    assert list_import_rows("tenant-a", import_a)
    assert list_import_rows("tenant-b", import_b)
    assert list_import_rows("tenant-a", import_b) == []
    assert list_import_rows("tenant-b", import_a) == []
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO workforce_import_rows (
                    organization_id, workforce_import_id, source_sheet,
                    source_row_number, source_reference, source_record_key,
                    row_kind, raw_payload
                ) VALUES (
                    'tenant-b', ?, 'Invalid', 1, 'Invalid:row:1',
                    'identity:invalid', 'identity', '{}'
                )
                """,
                (import_a,),
            )


def test_unresolved_source_identity_is_preserved_without_member_creation():
    organization_id = "unresolved-source-tenant"
    content = _book(include_unresolved=True)
    result = _in_organization(organization_id, lambda: _apply(content))
    rows = list_import_rows(organization_id, _import_id(organization_id))
    unresolved = [
        item for item in rows if item.transporter_id == "A987654321"
    ]

    assert result.members_created == 1
    assert result.statuses_created == 1
    assert len(unresolved) == 2
    assert {item.row_kind for item in unresolved} == {"identity", "shift"}
    assert all(item.resolved_workforce_member_id is None for item in unresolved)
    assert all(item.source_external_identifier is None for item in unresolved)
    assert all(item.driver_display_name is None for item in unresolved)
    assert next(
        item for item in unresolved if item.row_kind == "shift"
    ).operational_date == "2026-08-10"


def test_source_rows_roll_back_with_failed_import(monkeypatch):
    organization_id = "rollback-source-tenant"
    parsed = interpret_workforce_workbook(_book(), "rollback.xlsx")
    original = import_repository._persist_source_rows

    def fail_after_rows(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic source row failure")

    monkeypatch.setattr(import_repository, "_persist_source_rows", fail_after_rows)
    with pytest.raises(RuntimeError, match="Synthetic source row failure"):
        _in_organization(
            organization_id,
            lambda: import_repository.apply_import(
                parsed,
                original_filename="rollback.xlsx",
                actor="test",
            ),
        )

    with db_session() as conn:
        for table in (
            "workforce_import_rows", "workforce_imports",
            "workforce_members", "workforce_day_statuses", "workforce_changes",
        ):
            assert conn.execute(
                f"SELECT COUNT(*) AS total FROM {table} "
                "WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()["total"] == 0


def test_legacy_import_without_rows_and_workspace_reset_are_supported():
    organization_id = "legacy-source-tenant"
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets,
                summary, organization_id
            ) VALUES (?, 'legacy.xlsx', '2026-01-01T00:00:00Z', '[]', '{}', ?)
            """,
            ("legacy-fingerprint", organization_id),
        )
        legacy_id = int(cursor.lastrowid)
    assert list_import_rows(organization_id, legacy_id) == []

    _in_organization(organization_id, lambda: _apply(_book(), "new.xlsx"))
    reset = _in_organization(
        organization_id,
        lambda: reset_workspace(actor="test"),
    )
    assert reset.removed_counts.workforce_import_rows == 2
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_import_rows "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()["total"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_imports "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()["total"] == 0


def test_schema_is_idempotent_and_postgres_translation_is_supported():
    init_schema()
    init_schema()
    with db_session() as conn:
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(workforce_import_rows)"
            ).fetchall()
        }
        indexes = {
            row["name"]
            for row in conn.execute(
                "PRAGMA index_list(workforce_import_rows)"
            ).fetchall()
        }
    assert {
        "organization_id", "workforce_import_id", "source_sheet",
        "source_row_number", "transporter_id", "operational_date",
        "raw_payload", "resolved_workforce_member_id",
    } <= columns
    assert "idx_workforce_import_rows_scope" in indexes
    translated = _postgres_schema_statement(
        "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    assert translated == "id SERIAL PRIMARY KEY"

import io
import json
from time import perf_counter

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_distribution_service
from app.plugins.workforce.application.contact_coverage_service import contact_coverage
from app.plugins.workforce.application import workforce_service
from app.plugins.workforce.importer.workbook_interpreter import interpret_workforce_workbook


BASE = "/api/plugins/workforce/v1"


def _book(headers: list[str], rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Anagrafica DSP"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def _apply(content: bytes, organization_id: str = "default", filename: str = "contacts.xlsx"):
    token = bind_organization(organization_id)
    try:
        preview = workforce_service.preview_import(content, filename)
        result = workforce_service.apply_import(
            content, filename, preview.fingerprint, actor="contact-test",
        )
        return preview, result
    finally:
        reset_organization(token)


def _member(identifier: str, *, organization_id: str = "default",
            phone: str | None = None, email: str | None = None,
            active: int = 1) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO workforce_members (
                   external_identifier, display_name, capabilities, active,
                   source_reference, created_at, updated_at, organization_id,
                   phone, email
               ) VALUES (?, ?, '[]', ?, 'contact-test',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', ?, ?, ?)""",
            (identifier, f"Driver {identifier}", active, organization_id, phone, email),
        )
        return int(cursor.lastrowid)


def _planning(organization_id: str = "default") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO driver_shift_plannings (
                   organization_id, label, period_start, period_end, status,
                   version, created_at, created_by, updated_at,
                   published_at, published_by
               ) VALUES (?, 'Contact QA', '2026-08-17', '2026-08-23', 'ACTIVE',
                         1, '2026-08-11T09:00:00Z', 'qa@test',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', 'qa@test')""",
            (organization_id,),
        )
        return int(cursor.lastrowid)


def _publish(planning_id: int, member_id: int, *, organization_id: str = "default") -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO driver_shift_planning_published_rows (
                   organization_id, driver_shift_planning_id, planning_version,
                   workforce_member_id, operational_date, status_code, availability,
                   shift_code, station, provenance_summary, published_at
               ) VALUES (?, ?, 1, ?, '2026-08-17', 'scheduled', 1,
                         'A', 'DLO2', '[]', '2026-08-11T09:00:00Z')""",
            (organization_id, planning_id, member_id),
        )


def _stored(identifier: str = "D-1", organization_id: str = "default"):
    with db_session() as conn:
        return conn.execute(
            """SELECT * FROM workforce_members
               WHERE organization_id=? AND external_identifier=?""",
            (organization_id, identifier),
        ).fetchone()


def test_phone_alias_italiano_is_detected():
    parsed = interpret_workforce_workbook(
        _book(["Matricola", "Driver", "Telefono"], [["D-1", "Uno", "3331234567"]]),
        "italiano.xlsx",
    )
    assert parsed.preview.phone_detected == 1
    assert parsed.members[0].phone == "+393331234567"


def test_phone_alias_inglese_is_detected_without_fuzzy_headers():
    exact = interpret_workforce_workbook(
        _book(["Driver ID", "Driver", "Phone Number"], [["D-1", "Uno", "+393331234567"]]),
        "english.xlsx",
    )
    fuzzy = interpret_workforce_workbook(
        _book(["Driver ID", "Driver", "Phone reference"], [["D-1", "Uno", "+393331234567"]]),
        "fuzzy.xlsx",
    )
    assert exact.preview.phone_detected == 1
    assert fuzzy.preview.phone_detected == 0


def test_email_alias_is_detected():
    parsed = interpret_workforce_workbook(
        _book(["Matricola", "Driver", "E-mail"], [["D-1", "Uno", "driver@example.test"]]),
        "email.xlsx",
    )
    assert parsed.preview.email_detected == 1


def test_phone_is_normalized_deterministically():
    _apply(_book(
        ["Matricola", "Driver", "Cellulare"],
        [["D-1", "Uno", "0039 333-123-4567"]],
    ))
    assert _stored()["phone"] == "+393331234567"


def test_email_is_trimmed_and_lowercased():
    _apply(_book(
        ["Matricola", "Driver", "Indirizzo email"],
        [["D-1", "Uno", " DRIVER@Example.Test "]],
    ))
    assert _stored()["email"] == "driver@example.test"


def test_invalid_phone_is_reported_and_remains_invalid_for_readiness():
    preview, _ = _apply(_book(
        ["Matricola", "Driver", "Telefono"], [["D-1", "Uno", "123"]],
    ))
    assert preview.invalid_contacts == 1
    assert contact_coverage("default").phone_invalid == 1


def test_invalid_email_is_reported_and_remains_invalid_for_readiness():
    preview, _ = _apply(_book(
        ["Matricola", "Driver", "Email"], [["D-1", "Uno", "not-an-email"]],
    ))
    assert preview.invalid_contacts == 1
    assert contact_coverage("default").email_invalid == 1


def test_missing_contact_fields_preserve_existing_values():
    _member("D-1", phone="+393331234567", email="driver@example.test")
    _apply(_book(["Matricola", "Driver"], [["D-1", "Uno"]]))
    row = _stored()
    assert row["phone"] == "+393331234567"
    assert row["email"] == "driver@example.test"


def test_valid_source_updates_existing_contacts():
    _member("D-1", phone="+393330000000", email="old@example.test")
    _apply(_book(
        ["Matricola", "Driver", "Telefono", "Email"],
        [["D-1", "Uno", "3331234567", "new@example.test"]],
    ))
    row = _stored()
    assert row["phone"] == "+393331234567"
    assert row["email"] == "new@example.test"


def test_invalid_source_does_not_overwrite_valid_existing_contacts():
    _member("D-1", phone="+393331234567", email="valid@example.test")
    _apply(_book(
        ["Matricola", "Driver", "Telefono", "Email"],
        [["D-1", "Uno", "invalid", "invalid"]],
    ))
    row = _stored()
    assert row["phone"] == "+393331234567"
    assert row["email"] == "valid@example.test"


def test_duplicate_phone_conflict_is_not_resolved_arbitrarily():
    preview, _ = _apply(_book(
        ["Matricola", "Driver", "Telefono"],
        [["D-1", "Uno", "3331234567"], ["D-1", "Uno", "3339999999"]],
    ))
    assert preview.contact_conflicts == 1
    assert _stored()["phone"] is None


def test_duplicate_email_conflict_is_not_resolved_arbitrarily():
    preview, _ = _apply(_book(
        ["Matricola", "Driver", "Email"],
        [["D-1", "Uno", "one@example.test"], ["D-1", "Uno", "two@example.test"]],
    ))
    assert preview.contact_conflicts == 1
    assert _stored()["email"] is None


def test_contact_coverage_is_organization_scoped():
    _member("D-1", phone="+393331234567")
    _member("OTHER", organization_id="other", email="other@example.test")
    model = contact_coverage("default")
    assert model.total_members == 1
    assert model.phone_valid == 1
    assert model.email_valid == 0


def test_coverage_counts_valid_invalid_missing_both_and_no_channel():
    _member("D-1", phone="+393331234567", email="one@example.test")
    _member("D-2", phone="bad", email=None)
    _member("D-3", phone=None, email="three@example.test", active=0)
    model = contact_coverage("default")
    assert model.model_dump() | {} == model.model_dump()
    assert (model.total_members, model.active_members) == (3, 2)
    assert (model.phone_valid, model.phone_invalid, model.phone_missing) == (1, 1, 1)
    assert (model.email_valid, model.email_invalid, model.email_missing) == (2, 0, 1)
    assert (model.both_valid, model.no_channel) == (1, 1)


def test_no_active_planning_returns_no_invented_recipient_metrics():
    _member("D-1", phone="+393331234567")
    model = contact_coverage("default")
    assert model.active_planning_available is False
    assert model.active_planning_id is None
    assert model.recipients_total is None
    assert model.recipients_no_channel is None


def test_active_planning_coverage_uses_real_published_recipients():
    planning_id = _planning()
    for index in range(10):
        phone = f"+3933300000{index:02d}" if index < 8 else None
        email = f"driver{index}@example.test" if index < 4 or index == 8 else None
        member_id = _member(f"D-{index}", phone=phone, email=email)
        _publish(planning_id, member_id)
    model = contact_coverage("default")
    assert model.active_planning_available is True
    assert model.active_planning_id == planning_id
    assert model.recipients_total == 10
    assert model.recipients_phone_ready == 8
    assert model.recipients_email_ready == 5
    assert model.recipients_both == 4
    assert model.recipients_no_channel == 1


def test_delivery_readiness_reflects_contacts_immediately_after_import():
    _apply(_book(
        ["Matricola", "Driver", "Telefono"],
        [["D-1", "Uno", "3331234567"], ["D-2", "Due", None]],
    ))
    planning_id = _planning()
    for identifier in ("D-1", "D-2"):
        _publish(planning_id, int(_stored(identifier)["id"]))
    model = driver_shift_distribution_service.prepare_distribution(
        "default", planning_id, "qa@test",
    )
    assert model.summary.contact_ready == 1
    assert model.summary.missing_contact == 1


def test_contacts_are_not_leaked_to_logs_audit_or_immutable_source_rows(caplog):
    phone = "+393331234567"
    email = "private@example.test"
    _apply(_book(
        ["Matricola", "Driver", "Telefono", "Email"],
        [["D-1", "Uno", phone, email]],
    ))
    with db_session() as conn:
        audits = conn.execute(
            "SELECT before_value, after_value FROM workforce_changes"
        ).fetchall()
        payloads = conn.execute(
            "SELECT raw_payload FROM workforce_import_rows"
        ).fetchall()
    serialized = json.dumps([tuple(row) for row in audits]) + json.dumps([tuple(row) for row in payloads])
    assert phone not in serialized and email not in serialized
    assert phone not in caplog.text and email not in caplog.text


def test_contact_changes_have_specific_safe_audit_events():
    _member("D-1")
    _apply(_book(
        ["Matricola", "Driver", "Telefono", "Email"],
        [["D-1", "Uno", "3331234567", "driver@example.test"]],
    ))
    with db_session() as conn:
        rows = conn.execute(
            """SELECT reason, before_value, after_value FROM workforce_changes
               WHERE reason IN ('phone_changed', 'email_changed') ORDER BY reason"""
        ).fetchall()
    assert {row["reason"] for row in rows} == {"phone_changed", "email_changed"}
    assert all("[present]" in row["after_value"] for row in rows)
    assert all("3331234567" not in row["after_value"] for row in rows)


def test_import_500_members_with_contacts_has_no_perceived_delay():
    rows = [
        [f"D-{index}", f"Driver {index}", f"333{index:07d}", f"driver{index}@example.test"]
        for index in range(500)
    ]
    content = _book(["Matricola", "Driver", "Telefono", "Email"], rows)
    started = perf_counter()
    preview, result = _apply(content, filename="contacts-500.xlsx")
    elapsed = perf_counter() - started
    assert preview.phone_detected == preview.email_detected == 500
    assert result.members_created == 500
    assert elapsed < 5.0


def test_contact_coverage_api_is_admin_safe_and_count_only():
    _member(
        "D-1",
        organization_id="test-organization",
        phone="+393331234567",
        email="driver@example.test",
    )
    response = TestClient(app).get(f"{BASE}/contact-coverage")
    assert response.status_code == 200
    body = response.json()
    assert body["phone_valid"] == body["email_valid"] == 1
    serialized = json.dumps(body)
    assert "3331234567" not in serialized and "driver@example.test" not in serialized

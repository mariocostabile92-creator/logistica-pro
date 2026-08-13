import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.database import db_session
from app.main import app


BASE = "/api/plugins/workforce/v1"
client = TestClient(app)


def _book(rows: list[list[object]], headers: list[str] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Anagrafica"
    sheet.append(headers or ["Matricola", "Nome Cognome", "Ciclo operativo"])
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _import(content: bytes):
    files = {"file": ("workforce-cycle.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    preview = client.post(f"{BASE}/import/preview", files=files)
    assert preview.status_code == 200, preview.text
    files = {"file": ("workforce-cycle.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    result = client.post(
        f"{BASE}/import",
        data={"confirmed_fingerprint": preview.json()["fingerprint"]},
        files=files,
    )
    assert result.status_code == 200, result.text
    return preview.json()


def _create(identifier: str | None = "DRV-CYCLE", cycle: str | None = None):
    payload = {
        "first_name": "Mario",
        "last_name": "Rossi",
        "external_identifier": identifier,
    }
    if cycle is not None:
        payload["operational_cycle"] = cycle
    return client.post(f"{BASE}/members", json=payload)


def test_manual_driver_creation_supports_canonical_cycles_and_not_set_default():
    created = _create()
    assert created.status_code == 201
    assert created.json()["operational_cycle"] == "NOT_SET"

    next_day = _create("DRV-ND", "NEXT_DAY")
    same_day = _create("DRV-SD", "SAME_DAY")
    assert next_day.json()["operational_cycle"] == "NEXT_DAY"
    assert same_day.json()["operational_cycle"] == "SAME_DAY"
    assert next_day.json()["phone"] is None
    assert next_day.json()["email"] is None


def test_create_rejects_invalid_cycle_and_duplicate_external_identifier():
    assert _create("DUPLICATE", "NEXT_DAY").status_code == 201
    duplicate = _create("duplicate", "SAME_DAY")
    invalid = _create("INVALID-CYCLE", "NIGHT")
    assert duplicate.status_code == 422
    assert invalid.status_code == 422


def test_update_cycle_status_contract_and_audit_are_preserved():
    member = _create("UPDATE-CYCLE", "NEXT_DAY").json()
    updated = client.patch(
        f"{BASE}/members/{member['workforce_member_id']}",
        json={
            "operational_cycle": "SAME_DAY",
            "employment_type": "full-time",
            "active": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["operational_cycle"] == "SAME_DAY"
    assert updated.json()["employment_type"] == "full-time"
    assert updated.json()["active"] is False
    with db_session() as conn:
        rows = conn.execute(
            "SELECT reason, before_value, after_value FROM workforce_changes WHERE entity_id = ?",
            (str(member["workforce_member_id"]),),
        ).fetchall()
    reasons = {row["reason"] for row in rows}
    assert {"driver_created", "operational_cycle_changed", "contract_changed"} <= reasons
    serialized = " ".join(str(row["before_value"]) + str(row["after_value"]) for row in rows)
    assert '"phone": null' in serialized
    assert '"email": null' in serialized


def test_legacy_member_defaults_to_not_set_after_idempotent_migration():
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("LEGACY", "Legacy Driver", "[]", 1, "legacy", "2026-08-01", "2026-08-01"),
        )
        member_id = int(cursor.lastrowid)
    member = next(item for item in client.get(f"{BASE}/members").json()["items"] if item["workforce_member_id"] == member_id)
    assert member["operational_cycle"] == "NOT_SET"


def test_import_normalizes_cycles_and_reports_preview_counts():
    preview = _import(_book([
        ["IMP-ND", "Driver Next", "NEXT-DAY"],
        ["IMP-SD", "Driver Same", "SD"],
        ["IMP-BAD", "Driver Unknown", "overnight"],
    ]))
    assert preview["next_day_detected"] == 1
    assert preview["same_day_detected"] == 1
    assert preview["operational_cycle_unrecognized"] == 1
    members = {item["external_identifier"]: item for item in client.get(f"{BASE}/members").json()["items"]}
    assert members["IMP-ND"]["operational_cycle"] == "NEXT_DAY"
    assert members["IMP-SD"]["operational_cycle"] == "SAME_DAY"
    assert members["IMP-BAD"]["operational_cycle"] == "NOT_SET"


def test_missing_invalid_and_conflicting_import_values_preserve_canonical_cycle():
    _import(_book([["PRESERVE", "Driver Preserve", "NEXT DAY"]]))
    _import(_book(
        [["PRESERVE", "Driver Preserve", "driver"]],
        ["Matricola", "Nome Cognome", "Ruolo"],
    ))
    assert client.get(f"{BASE}/members").json()["items"][0]["operational_cycle"] == "NEXT_DAY"

    _import(_book([["PRESERVE", "Driver Preserve", "invalid cycle"]]))
    assert client.get(f"{BASE}/members").json()["items"][0]["operational_cycle"] == "NEXT_DAY"

    preview = _import(_book([
        ["PRESERVE", "Driver Preserve", "NEXT DAY"],
        ["PRESERVE", "Driver Preserve", "SAME DAY"],
    ]))
    assert preview["operational_cycle_unrecognized"] == 1
    assert any("Conflitto ciclo operativo" in item for item in preview["anomalies"])
    assert client.get(f"{BASE}/members").json()["items"][0]["operational_cycle"] == "NEXT_DAY"


def test_same_external_identifier_is_isolated_by_organization():
    def tenant(name: str, email: str) -> TestClient:
        tenant_client = TestClient(app, headers={"X-Auth-Enforce": "1"})
        response = tenant_client.post("/api/auth/register", json={
            "organization": {"name": name, "primary_station": "DLO2", "timezone": "Europe/Rome", "language": "it"},
            "administrator": {
                "first_name": "Tenant", "last_name": "Admin", "email": email,
                "password": "Password-sicura-123", "password_confirmation": "Password-sicura-123",
            },
        })
        assert response.status_code == 201
        return tenant_client

    first = tenant("Cycle A", "cycle-a@example.test")
    second = tenant("Cycle B", "cycle-b@example.test")
    payload = {"first_name": "Same", "last_name": "Identifier", "external_identifier": "SHARED", "operational_cycle": "NEXT_DAY"}
    assert first.post(f"{BASE}/members", json=payload).status_code == 201
    payload["operational_cycle"] = "SAME_DAY"
    assert second.post(f"{BASE}/members", json=payload).status_code == 201
    assert [item["operational_cycle"] for item in first.get(f"{BASE}/members").json()["items"]] == ["NEXT_DAY"]
    assert [item["operational_cycle"] for item in second.get(f"{BASE}/members").json()["items"]] == ["SAME_DAY"]

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.infrastructure import write_repository
from app.plugins.workforce.infrastructure import read_repository


BASE = "/api/plugins/workforce/v1"
client = TestClient(app)


def _member(identifier: str, cycle: str = "NOT_SET") -> dict:
    response = client.post(f"{BASE}/members", json={
        "first_name": identifier,
        "last_name": "Driver",
        "external_identifier": identifier,
        "operational_cycle": cycle,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _batch(member_id: int, dates: list[str], activity: str | None = None):
    return client.post(f"{BASE}/day-status/batch", json={
        "workforce_member_id": member_id,
        "dates": dates,
        "status_code": "scheduled",
        "shift_code": "C1",
        "operational_activity": activity,
    })


def _workbook(activity: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planning"
    sheet.append(["Matricola", "Nome Cognome", "Data", "Turno", "Attività operativa"])
    sheet.append(["IMPORT-ACT", "Import Activity", "2026-08-10", "C1", activity])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _import(content: bytes):
    files = {"file": ("activity.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    preview = client.post(f"{BASE}/import/preview", files=files)
    assert preview.status_code == 200, preview.text
    files = {"file": ("activity.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    result = client.post(f"{BASE}/import", data={
        "confirmed_fingerprint": preview.json()["fingerprint"],
    }, files=files)
    assert result.status_code == 200, result.text


def test_planning_read_model_uses_canonical_cycle_for_all_three_states():
    _member("NEXT", "NEXT_DAY")
    _member("SAME", "SAME_DAY")
    _member("UNSET")
    items = {item["external_identifier"]: item for item in client.get(f"{BASE}/members").json()["items"]}
    assert items["NEXT"]["operational_cycle"] == "NEXT_DAY"
    assert items["SAME"]["operational_cycle"] == "SAME_DAY"
    assert items["UNSET"]["operational_cycle"] == "NOT_SET"


def test_cycle_lookup_is_scoped_to_the_requested_organization():
    write_repository.create_member({
        "first_name": "Org A",
        "last_name": "Driver",
        "external_identifier": "SHARED-CYCLE-ID",
        "operational_cycle": "NEXT_DAY",
    }, "tester", "organization-a")
    write_repository.create_member({
        "first_name": "Org B",
        "last_name": "Driver",
        "external_identifier": "SHARED-CYCLE-ID",
        "operational_cycle": "SAME_DAY",
    }, "tester", "organization-b")
    org_a = read_repository.find_members_by_external_identifier(
        "organization-a", "SHARED-CYCLE-ID",
    )
    org_b = read_repository.find_members_by_external_identifier(
        "organization-b", "SHARED-CYCLE-ID",
    )
    assert [item.operational_cycle.value for item in org_a] == ["NEXT_DAY"]
    assert [item.operational_cycle.value for item in org_b] == ["SAME_DAY"]


def test_batch_persists_shift_and_activity_without_copying_driver_cycle():
    member = _member("BATCH", "NEXT_DAY")
    response = _batch(member["workforce_member_id"], ["2026-08-10", "2026-08-11"], "Consegna DLO2")
    assert response.status_code == 200, response.text
    assert {(item["shift_code"], item["operational_activity"]) for item in response.json()["items"]} == {
        ("C1", "Consegna DLO2")
    }
    with db_session() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(workforce_day_statuses)").fetchall()}
    assert "operational_activity" in columns
    assert "operational_cycle" not in columns


def test_legacy_batch_without_activity_preserves_existing_activity_and_explicit_null_clears_it():
    member = _member("BACKWARD")
    day = "2026-08-10"
    assert _batch(member["workforce_member_id"], [day], "Consegna").status_code == 200
    legacy = client.post(f"{BASE}/day-status/batch", json={
        "workforce_member_id": member["workforce_member_id"],
        "dates": [day],
        "status_code": "scheduled",
        "shift_code": "SA",
    })
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["items"][0]["operational_activity"] == "Consegna"
    cleared = _batch(member["workforce_member_id"], [day], None)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["items"][0]["operational_activity"] is None


def test_batch_is_atomic_and_organization_scoped(monkeypatch):
    member = _member("ATOMIC")
    with db_session() as conn:
        organization_id = conn.execute(
            "SELECT organization_id FROM workforce_members WHERE id = ?",
            (member["workforce_member_id"],),
        ).fetchone()["organization_id"]
    original = write_repository._save_batch_status
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated activity failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(write_repository, "_save_batch_status", fail_second)
    with pytest.raises(RuntimeError, match="simulated activity failure"):
        write_repository.save_manual_statuses_batch({
            "workforce_member_id": member["workforce_member_id"],
            "status_code": "scheduled",
            "availability": True,
            "shift_code": "C1",
            "operational_activity": "Attività test",
        }, ["2026-08-10", "2026-08-11"], "tester", organization_id)
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM workforce_day_statuses").fetchone()["total"] == 0


def test_copy_week_preserves_activity_and_never_invents_missing_values():
    member = _member("COPY")
    assert _batch(member["workforce_member_id"], ["2026-08-10"], "Consegna").status_code == 200
    assert _batch(member["workforce_member_id"], ["2026-08-11"], None).status_code == 200
    preview = client.get(f"{BASE}/week-copy/preview", params={
        "workforce_member_id": member["workforce_member_id"],
        "target_week_start": "2026-08-17",
    }).json()
    result = client.post(f"{BASE}/week-copy", json={
        "workforce_member_id": member["workforce_member_id"],
        "target_week_start": "2026-08-17",
        "expected_fingerprint": preview["fingerprint"],
    })
    assert result.status_code == 200, result.text
    copied = {item["date"]: item for item in result.json()["items"]}
    assert copied["2026-08-17"]["operational_activity"] == "Consegna"
    assert copied["2026-08-18"]["operational_activity"] is None


def test_explicit_activity_import_is_preserved_and_missing_import_does_not_erase_it():
    _import(_workbook("Attività reale"))
    calendar = client.get(f"{BASE}/calendar", params={"date_from": "2026-08-10", "date_to": "2026-08-10"}).json()
    assert calendar["items"][0]["operational_activity"] == "Attività reale"
    with db_session() as conn:
        source = conn.execute("SELECT operational_activity FROM workforce_import_rows WHERE row_kind='shift'").fetchone()
    assert source["operational_activity"] == "Attività reale"


def test_no_cycle_activity_compatibility_rule_is_invented():
    member = _member("NO-RULE", "SAME_DAY")
    response = _batch(member["workforce_member_id"], ["2026-08-10"], "Qualsiasi attività controllata")
    assert response.status_code == 200
    body = response.json()["items"][0]
    assert body["operational_activity"] == "Qualsiasi attività controllata"
    assert "compat" not in body

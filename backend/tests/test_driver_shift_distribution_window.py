import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.infrastructure.schema import (
    _migrate_driver_shift_distribution_window_uniqueness,
)
from tests.test_driver_shift_distribution import BASE, ORG, _member, _planning, _shift


WINDOW_A = {"period_start": "2026-08-10", "period_end": "2026-08-16"}
WINDOW_B = {"period_start": "2026-08-17", "period_end": "2026-08-23"}


def _annual_scenario():
    planning_id = _planning(
        label="Planning annuale QA",
        period_start="2025-12-28",
        period_end="2027-01-03",
    )
    mario = _member("ANNUAL-1", "Mario Rossi")
    anna = _member("ANNUAL-2", "Anna Verdi")
    luca = _member("ANNUAL-3", "Luca Bianchi")
    _shift(planning_id, mario, "2026-08-10")
    _shift(planning_id, mario, "2026-08-17", shift="B")
    _shift(planning_id, anna, "2026-08-15")
    _shift(planning_id, luca, "2026-08-20")
    return planning_id, mario, anna, luca


def _prepare(client, planning_id, window):
    response = client.post(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution",
        json=window,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _portal_and_credentials(client, distribution_id):
    credentials = client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/credentials/prepare"
    ).json()
    portal = client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/portal"
    ).json()
    return credentials, portal["access_url"].split("#token=", 1)[1]


def _public():
    return TestClient(app, headers={"X-Test-Auth-Harness": ""})


def _login(client, portal_token, credential):
    return client.post(
        "/api/public/driver-shifts/portal/login",
        json={
            "portal_token": portal_token,
            "access_code": credential["access_code"],
            "pin": credential["initial_pin"],
            "remember_device": False,
        },
    )


def test_week_window_is_persisted_without_mutating_annual_planning():
    planning_id, _, _, _ = _annual_scenario()
    model = _prepare(TestClient(app), planning_id, WINDOW_A)
    assert model["distribution"]["period_start"] == WINDOW_A["period_start"]
    assert model["distribution"]["period_end"] == WINDOW_A["period_end"]
    with db_session() as conn:
        planning = conn.execute(
            "SELECT period_start, period_end FROM driver_shift_plannings WHERE id=?",
            (planning_id,),
        ).fetchone()
    assert dict(planning) == {"period_start": "2025-12-28", "period_end": "2027-01-03"}


def test_recipients_come_only_from_published_rows_inside_window():
    planning_id, _, _, _ = _annual_scenario()
    model = _prepare(TestClient(app), planning_id, WINDOW_A)
    assert {item["display_name"] for item in model["recipients"]} == {
        "Mario Rossi", "Anna Verdi",
    }
    assert [item["shift_days_count"] for item in model["recipients"]] == [1, 1]


def test_same_revision_and_window_is_idempotent_but_second_week_is_distinct():
    planning_id, _, _, _ = _annual_scenario()
    client = TestClient(app)
    first = _prepare(client, planning_id, WINDOW_A)
    repeated = _prepare(client, planning_id, WINDOW_A)
    second = _prepare(client, planning_id, WINDOW_B)
    assert first["distribution"]["id"] == repeated["distribution"]["id"]
    assert second["distribution"]["id"] != first["distribution"]["id"]
    with db_session() as conn:
        rows = conn.execute(
            "SELECT period_start, period_end, status FROM driver_shift_distributions ORDER BY id"
        ).fetchall()
    assert [(row["period_start"], row["period_end"], row["status"]) for row in rows] == [
        ("2026-08-10", "2026-08-16", "READY"),
        ("2026-08-17", "2026-08-23", "READY"),
    ]


def test_window_outside_active_planning_is_rejected_with_400():
    planning_id, _, _, _ = _annual_scenario()
    response = TestClient(app).post(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution",
        json={"period_start": "2027-01-04", "period_end": "2027-01-10"},
    )
    assert response.status_code == 400
    assert "contenuto" in response.text


def test_personal_link_exposes_only_rows_inside_distribution_window():
    planning_id, _, _, _ = _annual_scenario()
    admin = TestClient(app)
    model = _prepare(admin, planning_id, WINDOW_A)
    mario = next(item for item in model["recipients"] if item["display_name"] == "Mario Rossi")
    link = admin.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}"
        f"/recipients/{mario['id']}/access-link"
    ).json()["access_url"]
    body = _public().get(f"/api/public/driver-shifts/{link.split('#token=', 1)[1]}").json()
    assert [item["operational_date"] for item in body["shifts"]] == ["2026-08-10"]


def test_shared_portal_session_exposes_only_selected_week():
    planning_id, _, _, _ = _annual_scenario()
    admin = TestClient(app)
    model = _prepare(admin, planning_id, WINDOW_A)
    credentials, portal_token = _portal_and_credentials(
        admin, model["distribution"]["id"],
    )
    mario_credential = next(
        item for item in credentials["initial_credentials"]
        if item["display_name"] == "Mario Rossi"
    )
    driver = _public()
    assert _login(driver, portal_token, mario_credential).status_code == 200
    body = driver.get("/api/public/driver-shifts/me/shifts").json()
    assert body["period_start"] == "2026-08-10"
    assert body["period_end"] == "2026-08-16"
    assert sum(len(day["shifts"]) for day in body["days"] if not day["missing"]) == 1
    assert "2026-08-17" not in str(body)


def test_credentials_are_reused_across_weekly_distributions():
    planning_id, _, _, _ = _annual_scenario()
    admin = TestClient(app)
    first = _prepare(admin, planning_id, WINDOW_A)
    first_credentials, _ = _portal_and_credentials(admin, first["distribution"]["id"])
    second = _prepare(admin, planning_id, WINDOW_B)
    second_credentials = admin.post(
        f"{BASE}/driver-shift-distributions/{second['distribution']['id']}/credentials/prepare"
    ).json()
    assert second_credentials["summary"]["already_existing"] == 1
    assert second_credentials["summary"]["newly_created"] == 1
    assert {item["display_name"] for item in second_credentials["initial_credentials"]} == {
        "Luca Bianchi",
    }
    assert first_credentials["initial_credentials"]


def test_acknowledgement_is_distribution_specific():
    planning_id, mario_id, _, _ = _annual_scenario()
    admin = TestClient(app)
    first = _prepare(admin, planning_id, WINDOW_A)
    credentials, portal_token = _portal_and_credentials(admin, first["distribution"]["id"])
    mario_credential = next(
        item for item in credentials["initial_credentials"]
        if item["display_name"] == "Mario Rossi"
    )
    first_driver = _public()
    _login(first_driver, portal_token, mario_credential)
    assert first_driver.post("/api/public/driver-shifts/me/acknowledge").status_code == 200

    second = _prepare(admin, planning_id, WINDOW_B)
    admin.post(
        f"{BASE}/driver-shift-distributions/{second['distribution']['id']}/credentials/prepare"
    )
    with db_session() as conn:
        statuses = conn.execute(
            """SELECT distribution_id, access_status
               FROM driver_shift_distribution_recipients
               WHERE workforce_member_id=? ORDER BY distribution_id""",
            (mario_id,),
        ).fetchall()
    assert [(row["distribution_id"], row["access_status"]) for row in statuses] == [
        (first["distribution"]["id"], "ACKNOWLEDGED"),
        (second["distribution"]["id"], "NOT_OPENED"),
    ]


def test_shared_portal_includes_recipient_without_phone_or_email():
    planning_id, _, _, _ = _annual_scenario()
    admin = TestClient(app)
    model = _prepare(admin, planning_id, WINDOW_A)
    assert model["summary"]["recipients_total"] == 2
    assert model["summary"]["missing_contact"] == 2
    credentials, token = _portal_and_credentials(admin, model["distribution"]["id"])
    assert credentials["summary"]["credentials_ready"] == 2
    driver = _public()
    assert _login(driver, token, credentials["initial_credentials"][0]).status_code == 200


def test_second_week_recipient_set_does_not_leak_first_week_only_driver():
    planning_id, _, _, _ = _annual_scenario()
    model = _prepare(TestClient(app), planning_id, WINDOW_B)
    assert {item["display_name"] for item in model["recipients"]} == {
        "Mario Rossi", "Luca Bianchi",
    }
    assert "Anna Verdi" not in str(model)


def test_legacy_sqlite_uniqueness_migrates_without_losing_data_or_child_links(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-distribution.sqlite3")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE driver_shift_plannings (
            id INTEGER NOT NULL,
            organization_id TEXT NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (id, organization_id)
        );
        CREATE TABLE driver_shift_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id TEXT NOT NULL,
            driver_shift_planning_id INTEGER NOT NULL,
            planning_version INTEGER NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (driver_shift_planning_id, organization_id)
                REFERENCES driver_shift_plannings(id, organization_id),
            UNIQUE (organization_id, driver_shift_planning_id, planning_version),
            UNIQUE (id, organization_id)
        );
        CREATE TABLE driver_shift_distribution_recipients (
            id INTEGER PRIMARY KEY,
            organization_id TEXT NOT NULL,
            distribution_id INTEGER NOT NULL,
            FOREIGN KEY (distribution_id, organization_id)
                REFERENCES driver_shift_distributions(id, organization_id)
        );
        INSERT INTO driver_shift_plannings VALUES (1, 'org');
        INSERT INTO driver_shift_distributions VALUES (
            1, 'org', 1, 1, '2026-08-10', '2026-08-16', 'READY',
            '2026-08-12T08:00:00Z', 'qa', '2026-08-12T08:00:00Z'
        );
        INSERT INTO driver_shift_distribution_recipients VALUES (1, 'org', 1);
        """
    )

    _migrate_driver_shift_distribution_window_uniqueness(conn)

    child_parent = conn.execute(
        "PRAGMA foreign_key_list(driver_shift_distribution_recipients)"
    ).fetchone()["table"]
    assert child_parent == "driver_shift_distributions"
    assert conn.execute(
        "SELECT COUNT(*) total FROM driver_shift_distribution_recipients"
    ).fetchone()["total"] == 1
    conn.execute(
        """INSERT INTO driver_shift_distributions (
               organization_id, driver_shift_planning_id, planning_version,
               period_start, period_end, status, created_at, created_by, updated_at
           ) VALUES ('org', 1, 1, '2026-08-17', '2026-08-23', 'READY', 'now', 'qa', 'now')"""
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO driver_shift_distributions (
                   organization_id, driver_shift_planning_id, planning_version,
                   period_start, period_end, status, created_at, created_by, updated_at
               ) VALUES ('org', 1, 1, '2026-08-17', '2026-08-23', 'READY', 'now', 'qa', 'now')"""
        )
    conn.close()

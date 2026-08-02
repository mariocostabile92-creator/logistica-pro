from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.infrastructure.schema import init_schema


client = TestClient(app)
BASE = "/api/plugins/workforce/v1"


def _member(identifier: str, name: str, *, reserve: bool = False) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, first_name, last_name,
                role, station, employment_type, capabilities,
                operational_notes, is_reserve, active, source_reference,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identifier, name, name.split()[0], name.split()[-1],
                "driver", "DLO1", "full-time", '["license_b"]',
                "Disponibile per attivita urbana", int(reserve), 1,
                "workforce-foundation-test", "2026-08-02T08:00:00+00:00",
                "2026-08-02T08:00:00+00:00",
            ),
        )
        return int(cursor.lastrowid)


def _status(
    member_id: int,
    code: str,
    available: bool,
    notes: str | None = None,
    day: str = "2026-08-03",
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                notes, source_reference, observed_or_confirmed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                member_id, day, code, int(available), notes, "test",
                "manual", "2026-08-02T08:00:00+00:00",
            ),
        )


def test_foundation_answers_how_many_people_are_callable_without_creating_shifts():
    callable_id = _member("DRV-001", "Mario Rossi")
    reserve_id = _member("DRV-002", "Giulia Bianchi", reserve=True)
    sick_id = _member("DRV-003", "Luca Verdi")
    _status(callable_id, "available", True)
    _status(reserve_id, "scheduled", True)
    _status(sick_id, "sickness", False)
    _status(callable_id, "rest", False, day="2026-07-31")
    _status(callable_id, "scheduled", True, day="2026-08-01")
    _status(reserve_id, "rest", False, day="2026-07-31")
    _status(reserve_id, "scheduled", True, day="2026-08-01")

    response = client.get(f"{BASE}/foundation?operation_date=2026-08-03")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 3, "available": 2, "callable": 2, "limited": 0, "holiday": 0,
        "sickness": 1, "leave": 0, "rest": 0, "not_callable": 1,
        "reserves": 1,
        "at_limit": 0, "rest_recommended": 0,
        "insufficient_data": 1, "active_overrides": 0,
    }
    assert payload["drivers"][0]["convocation_status"] == "not_started"
    assert payload["drivers"][0]["consecutivity_status"] == "regolare"
    assert payload["drivers"][0]["callability_reason"]
    assert any("Planning" in item for item in payload["limitations"])


def test_profile_fields_are_persisted_without_turn_or_convocation_workflow():
    member_id = _member("DRV-010", "Nome Provvisorio")
    response = client.patch(
        f"{BASE}/members/{member_id}",
        json={
            "first_name": "Anna", "last_name": "Neri", "station": "DLO2",
            "operational_notes": "Abilitata van elettrico", "is_reserve": True,
        },
    )
    assert response.status_code == 200
    member = response.json()
    assert member["first_name"] == "Anna"
    assert member["last_name"] == "Neri"
    assert member["station"] == "DLO2"
    assert member["is_reserve"] is True


def test_workforce_profile_schema_migration_is_idempotent():
    init_schema()
    init_schema()
    with db_session() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(workforce_members)").fetchall()}
    assert {"first_name", "last_name", "station", "operational_notes", "is_reserve"} <= columns


def test_foundation_rejects_invalid_operation_date():
    response = client.get(f"{BASE}/foundation?operation_date=not-a-date")
    assert response.status_code == 422


def test_availability_engine_explains_callable_limited_and_not_callable_states():
    available = _member("DRV-A", "Driver Disponibile")
    limited = _member("DRV-L", "Driver Limitato")
    holiday = _member("DRV-F", "Driver Ferie")
    rest = _member("DRV-R", "Driver Riposo")
    _status(available, "available", True)
    _status(limited, "available_limited", True, "Limitazione manuale verificata.")
    _status(holiday, "holiday", False)
    _status(rest, "rest", False)
    for member_id in (available, limited):
        _status(member_id, "rest", False, day="2026-07-31")
        _status(member_id, "scheduled", True, day="2026-08-01")

    payload = client.get(f"{BASE}/foundation?operation_date=2026-08-03").json()
    by_id = {item["external_identifier"]: item for item in payload["drivers"]}
    assert by_id["DRV-A"]["callability_status"] == "callable"
    assert by_id["DRV-A"]["callability_reason"] == "Nessuna limitazione."
    assert by_id["DRV-L"]["callability_status"] == "limited"
    assert by_id["DRV-L"]["callability_reason"] == "Limitazione manuale verificata."
    assert by_id["DRV-F"]["callability_reason"] == "Ferie."
    assert by_id["DRV-R"]["callability_tone"] == "rest"
    assert all(item["callability_reason"] for item in payload["drivers"])
    assert payload["summary"]["limited"] == 1


def test_limited_availability_requires_an_explicit_reason_on_write():
    member_id = _member("DRV-LIMIT", "Driver Limitazione")
    missing = client.post(f"{BASE}/day-status", json={
        "workforce_member_id": member_id, "date": "2026-08-03",
        "status_code": "available_limited",
    })
    assert missing.status_code == 422
    saved = client.post(f"{BASE}/day-status", json={
        "workforce_member_id": member_id, "date": "2026-08-03",
        "status_code": "available_limited", "notes": "Guida solo van standard.",
    })
    assert saved.status_code == 200
    assert saved.json()["availability"] is True

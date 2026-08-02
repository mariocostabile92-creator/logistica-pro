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


def _status(member_id: int, code: str, available: bool) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                source_reference, observed_or_confirmed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                member_id, "2026-08-03", code, int(available), "test",
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

    response = client.get(f"{BASE}/foundation?operation_date=2026-08-03")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 3, "available": 2, "callable": 2, "holiday": 0,
        "sickness": 1, "leave": 0, "rest": 0, "not_callable": 1,
        "reserves": 1,
    }
    assert payload["drivers"][0]["convocation_status"] == "not_started"
    assert payload["drivers"][0]["consecutivity_status"] == "not_evaluated"
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

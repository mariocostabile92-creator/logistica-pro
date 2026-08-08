from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app


client = TestClient(app)
DAMAGE = "/api/fleet/damage-cases"
NOW = "2026-08-08T12:00:00+00:00"


def _member(identifier: str, name: str, organization_id: str = "test-organization") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'damage-history-test', ?, ?)
            """,
            (organization_id, identifier, name, NOW, NOW),
        )
        return int(cursor.lastrowid)


def _case(plate: str, member_id: int | None = None, source: str = "journal") -> dict:
    asset = client.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": f"history-{plate}",
            "plate": plate,
            "category": "van",
            "status": "active",
            "availability": "available",
        },
    ).json()
    payload = {
        "vehicle_id": asset["id"],
        "occurred_at": NOW,
        "origin": "manual",
        "manual_reason": "Test storico driver",
        "description": f"Danno sul mezzo {plate}",
        "severity": "media",
        "vehicle_operational_status": "disponibile",
    }
    if member_id is not None:
        payload.update({
            "workforce_member_id": member_id,
            "attribution_source": source,
        })
    response = client.post(DAMAGE, json=payload)
    assert response.status_code == 201
    return response.json()


def test_canonical_driver_filter_separates_histories_and_derives_counts():
    alessandro = _member("DRV-ALESSANDRO", "Alessandro Facchetti")
    giulia = _member("DRV-GIULIA", "Giulia Bianchi")
    first = _case("DH001AA", alessandro)
    second = _case("DH002AA", alessandro, "planning")
    _case("DH003AA", giulia)
    with db_session() as conn:
        conn.execute(
            "UPDATE damage_cases SET status='chiusa', closed_at=? WHERE id=?",
            (NOW, second["id"]),
        )

    response = client.get(DAMAGE, params={"workforce_member_id": alessandro})

    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["items"]} == {first["id"], second["id"]}
    assert all(item["driver_workforce_member_id"] == alessandro for item in body["items"])
    assert body["summary"] == {
        "total_cases": 2,
        "open_cases": 1,
        "closed_cases": 1,
    }


def test_driver_without_cases_and_foreign_driver_return_empty_history():
    empty_driver = _member("DRV-EMPTY", "Driver Senza Pratiche")
    foreign_driver = _member("DRV-FOREIGN-HISTORY", "Driver Altra Azienda", "other-org")

    empty = client.get(DAMAGE, params={"workforce_member_id": empty_driver}).json()
    foreign = client.get(DAMAGE, params={"workforce_member_id": foreign_driver}).json()

    expected = {"total_cases": 0, "open_cases": 0, "closed_cases": 0}
    assert empty == {"items": [], "summary": expected}
    assert foreign == {"items": [], "summary": expected}


def test_search_uses_readable_driver_snapshot_not_the_canonical_relation():
    member_id = _member("DRV-SEARCH", "Alessandro Facchetti")
    case = _case("DH004AA", member_id)

    result = client.get(DAMAGE, params={"search": "Alessandro"}).json()

    assert [item["id"] for item in result["items"]] == [case["id"]]


def test_unassigned_filter_handles_cases_without_driver():
    member_id = _member("DRV-ASSIGNED", "Mario Rossi")
    unassigned = _case("DH005AA")
    _case("DH006AA", member_id)

    result = client.get(DAMAGE, params={"driver_unassigned": True}).json()

    assert [item["id"] for item in result["items"]] == [unassigned["id"]]
    assert result["summary"] == {
        "total_cases": 1,
        "open_cases": 1,
        "closed_cases": 0,
    }


def test_history_counts_are_not_persisted_on_workforce_or_damage_cases():
    with db_session() as conn:
        damage_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(damage_cases)")
        }
        workforce_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(workforce_members)")
        }

    forbidden = {"total_cases", "open_cases", "closed_cases", "damage_count"}
    assert forbidden.isdisjoint(damage_columns)
    assert forbidden.isdisjoint(workforce_columns)

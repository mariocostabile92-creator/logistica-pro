from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
JOURNAL = "/api/plugins/fleet/v1/journal"
DAMAGE = "/api/fleet"


def asset():
    response = client.post("/api/plugins/fleet/v1/assets", json={
        "external_identifier": "damage-van-1", "plate": "DM010GE",
        "category": "van", "status": "active", "availability": "available",
    })
    assert response.status_code == 201
    return response.json()


def anomaly():
    created = asset()
    opened = client.post(f"{JOURNAL}/sessions", json={
        "operation_type": "check_in", "plate": "DM010GE",
        "declared_driver_identifier": "Mario Rossi",
    }).json()
    response = client.post(
        f"{JOURNAL}/sessions/{opened['id']}/complete",
        headers={"X-Journal-Token": opened["token"]},
        json={
            "odometer_km": 42100, "fuel_percentage": 35,
            "cleanliness_status": "compliant", "anomaly_present": True,
            "anomaly_description": "Graffio portiera destra",
            "equipment": [
                {"code": "telepass", "status": "present"},
                {"code": "phone", "status": "present"},
                {"code": "keys", "status": "present"},
                {"code": "fuel_card", "status": "present"},
            ],
            "client_submission_id": "damage-submission-1",
            "timezone": "Europe/Rome",
        },
    )
    assert response.status_code == 200
    return created, response.json()


def create_from_anomaly():
    created, _ = anomaly()
    candidate = client.get(f"{DAMAGE}/damage-candidates").json()["items"][0]
    response = client.post(f"{DAMAGE}/damage-cases", json={
        "vehicle_id": created["id"],
        "source_movement_id": candidate["movement_id"],
        "occurred_at": candidate["occurred_at"],
        "origin": "journal",
        "description": "precompilata dal Journal",
        "severity": "alta",
        "vehicle_operational_status": "fermo",
        "estimated_cost": "1250.50",
    })
    assert response.status_code == 201
    return response.json(), candidate


def test_journal_anomaly_creates_one_persistent_linked_case():
    case, candidate = create_from_anomaly()
    assert case["case_number"].startswith("DMG-")
    assert case["source_movement_id"] == candidate["movement_id"]
    assert case["source_document_id"].startswith("DOC-")
    assert case["declared_driver"] == "Mario Rossi"
    assert case["estimated_cost"] == "1250.50"
    assert case["estimated_cost_eur"] == "€ 1.250,50"
    assert Decimal(case["estimated_cost"]) == Decimal("1250.50")
    assert client.get(f"{DAMAGE}/damage-candidates").json()["items"] == []
    duplicate = client.post(f"{DAMAGE}/damage-cases", json={
        "vehicle_id": case["vehicle_id"],
        "source_movement_id": candidate["movement_id"],
        "occurred_at": candidate["occurred_at"],
        "origin": "journal", "description": "duplicata",
        "severity": "media", "vehicle_operational_status": "disponibile",
    })
    assert duplicate.status_code == 409


def test_manual_case_requires_reason_and_supports_search_filters_detail():
    created = asset()
    base = {
        "vehicle_id": created["id"], "occurred_at": "2026-07-30T10:00:00Z",
        "origin": "manual", "description": "Danno scoperto in deposito",
        "severity": "media", "vehicle_operational_status": "disponibile",
    }
    assert client.post(f"{DAMAGE}/damage-cases", json=base).status_code == 422
    base["manual_reason"] = "Segnalazione responsabile deposito"
    case = client.post(f"{DAMAGE}/damage-cases", json=base).json()
    assert client.get(f"{DAMAGE}/damage-cases/{case['id']}").status_code == 200
    assert len(client.get(f"{DAMAGE}/damage-cases", params={"search": "deposito"}).json()["items"]) == 1
    assert len(client.get(f"{DAMAGE}/damage-cases", params={"severity": "media"}).json()["items"]) == 1
    assert client.get(f"{DAMAGE}/damage-cases", params={"severity": "critica"}).json()["items"] == []


def test_status_rules_notes_timeline_and_vehicle_source_of_truth():
    case, _ = create_from_anomaly()
    vehicle = client.get(f"/api/plugins/fleet/v1/assets/{case['vehicle_id']}").json()
    assert vehicle["availability"] == "unavailable"
    invalid = client.post(f"{DAMAGE}/damage-cases/{case['id']}/status", json={
        "status": "chiusa", "note": "",
    })
    assert invalid.status_code == 422
    moved = client.post(f"{DAMAGE}/damage-cases/{case['id']}/status", json={
        "status": "in_valutazione", "note": "Valutazione avviata",
    })
    assert moved.status_code == 200
    note = client.post(f"{DAMAGE}/damage-cases/{case['id']}/notes", json={
        "note": "Contattata officina", "actor": "fleet_manager",
    })
    assert note.status_code == 200
    events = client.get(f"{DAMAGE}/damage-cases/{case['id']}/events").json()["items"]
    assert [event["event_type"] for event in events] == [
        "pratica_creata", "stato_modificato", "nota_aggiunta",
    ]


def test_close_and_reopen_require_explicit_notes():
    case, _ = create_from_anomaly()
    current = "nuova"
    for target in (
        "in_valutazione", "preventivo_richiesto", "preventivo_ricevuto",
        "riparazione_programmata", "in_riparazione", "chiusa",
    ):
        response = client.post(f"{DAMAGE}/damage-cases/{case['id']}/status", json={
            "status": target, "note": f"{current} → {target}",
        })
        assert response.status_code == 200
        current = target
    assert response.json()["closed_at"] is not None
    no_note = client.post(f"{DAMAGE}/damage-cases/{case['id']}/status", json={
        "status": "in_valutazione", "note": "",
    })
    assert no_note.status_code == 422
    reopened = client.post(f"{DAMAGE}/damage-cases/{case['id']}/status", json={
        "status": "in_valutazione", "note": "Nuovo danno emerso",
    })
    assert reopened.status_code == 200
    assert reopened.json()["closed_at"] is None
    assert reopened.json()["events"][-1]["event_type"] == "pratica_riaperta"

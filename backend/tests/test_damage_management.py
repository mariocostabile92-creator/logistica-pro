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
    assert vehicle["availability"] == "indisponibile"
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
        "pratica_creata", "stato_operativo_mezzo_modificato",
        "stato_modificato", "nota_aggiunta",
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
            **({"restoration_status": "disponibile"} if target == "chiusa" else {}),
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


def test_medium_does_not_block_and_critical_blocks_with_timeline():
    created = asset()
    base = {
        "vehicle_id": created["id"], "occurred_at": "2026-07-30T10:00:00Z",
        "origin": "manual", "manual_reason": "Controllo deposito",
        "description": "Verifica carrozzeria", "severity": "media",
        "vehicle_operational_status": "disponibile",
    }
    medium = client.post(f"{DAMAGE}/damage-cases", json=base)
    assert medium.status_code == 201
    assert medium.json()["operational_notice"] == (
        "Valutare eventuali limitazioni operative del mezzo."
    )
    assert client.get(
        f"/api/plugins/fleet/v1/assets/{created['id']}"
    ).json()["availability"] == "available"

    updated = client.patch(
        f"{DAMAGE}/damage-cases/{medium.json()['id']}",
        json={"severity": "critica"},
    )
    assert updated.status_code == 200
    assert updated.json()["asset_availability"] == "indisponibile"
    operational = [
        event for event in updated.json()["events"]
        if event["event_type"] == "stato_operativo_mezzo_modificato"
    ][-1]
    assert operational["previous_status"] == "disponibile"
    assert operational["new_status"] == "indisponibile"


def test_repair_states_and_closure_require_explicit_restoration():
    case, _ = create_from_anomaly()
    for target, expected in (
        ("in_valutazione", "indisponibile"),
        ("preventivo_richiesto", "indisponibile"),
        ("preventivo_ricevuto", "indisponibile"),
        ("riparazione_programmata", "in_manutenzione"),
        ("in_riparazione", "in_officina"),
    ):
        response = client.post(
            f"{DAMAGE}/damage-cases/{case['id']}/status",
            json={"status": target, "note": f"Passaggio a {target}"},
        )
        assert response.status_code == 200
        assert response.json()["asset_availability"] == expected
    no_choice = client.post(
        f"{DAMAGE}/damage-cases/{case['id']}/status",
        json={"status": "chiusa", "note": "Riparazione completata"},
    )
    assert no_choice.status_code == 422
    closed = client.post(
        f"{DAMAGE}/damage-cases/{case['id']}/status",
        json={
            "status": "chiusa", "note": "Collaudo completato",
            "restoration_status": "disponibile",
        },
    )
    assert closed.status_code == 200
    assert closed.json()["asset_availability"] == "disponibile"


def test_manual_unblock_requires_reason_and_other_open_case_remains_restrictive():
    case, _ = create_from_anomaly()
    blocked = client.patch(
        f"{DAMAGE}/damage-cases/{case['id']}",
        json={"vehicle_operational_status": "disponibile"},
    )
    assert blocked.status_code == 422
    confirmed = client.patch(
        f"{DAMAGE}/damage-cases/{case['id']}",
        json={
            "vehicle_operational_status": "disponibile",
            "operational_reason": "Verifica tecnica completata",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["asset_availability"] == "disponibile"
    held = client.patch(
        f"{DAMAGE}/damage-cases/{case['id']}",
        json={
            "vehicle_operational_status": "in_officina",
            "operational_reason": "Presa in carico officina",
        },
    )
    assert held.json()["asset_availability"] == "in_officina"

    second_payload = {
        "vehicle_id": case["vehicle_id"],
        "occurred_at": "2026-07-30T12:00:00Z", "origin": "manual",
        "manual_reason": "Seconda segnalazione", "description": "Danno critico",
        "severity": "critica", "vehicle_operational_status": "indisponibile",
    }
    second = client.post(f"{DAMAGE}/damage-cases", json=second_payload).json()
    closed = client.post(
        f"{DAMAGE}/damage-cases/{second['id']}/status",
        json={
            "status": "chiusa", "note": "Pratica amministrativa chiusa",
            "restoration_status": "disponibile",
        },
    )
    assert closed.status_code == 200
    assert closed.json()["asset_availability"] == "in_officina"


def test_manual_operational_status_without_damage_updates_asset_audit_and_planning():
    created = asset()
    response = client.patch(
        f"{DAMAGE}/vehicles/{created['id']}/operational-status",
        json={
            "status": "in_manutenzione",
            "reason": "Tagliando programmato",
            "origin": "parco_mezzi",
        },
    )
    assert response.status_code == 200
    assert response.json()["asset"]["availability"] == "in_manutenzione"
    events = client.get(
        f"/api/plugins/fleet/v1/assets/{created['id']}/events"
    ).json()["items"]
    event = events[-1]
    assert event["event_type"] == "stato_operativo_mezzo_modificato"
    assert event["details"]["previous"] == "available"
    assert event["details"]["current"] == "in_manutenzione"
    assert event["details"]["origin"] == "parco_mezzi"
    assert event["details"]["reason"] == "Tagliando programmato"
    availability = client.get(
        "/api/plugins/fleet/v1/availability"
    ).json()
    observed = next(
        item for item in availability
        if item["resource_identifier"] == created["external_identifier"]
    )
    assert observed["available"] is False
    assert observed["observed_state"] == "in_manutenzione"
    assert observed["reason"] == "Tagliando programmato"
    assert observed["origin"] == "parco_mezzi"
    detail = client.get(
        f"/api/plugins/fleet/v1/assets/{created['id']}"
    ).json()
    assert detail["operational_status"] == "in_manutenzione"
    assert detail["operational_status_reason"] == "Tagliando programmato"
    assert detail["operational_status_origin"] == "parco_mezzi"
    assert detail["operational_status_actor"] == "fleet_manager"
    assert detail["operational_status_updated_at"]
    assert detail["operational_status_damage_case_id"] is None

    second = client.patch(
        f"{DAMAGE}/vehicles/{created['id']}/operational-status",
        json={
            "status": "in_officina",
            "reason": "Trasferimento officina convenzionata",
            "origin": "vehicle_library",
        },
    )
    assert second.status_code == 200
    latest = client.get(
        f"/api/plugins/fleet/v1/assets/{created['id']}"
    ).json()
    assert latest["operational_status_reason"] == (
        "Trasferimento officina convenzionata"
    )
    assert latest["operational_status_origin"] == "vehicle_library"
    history = client.get(
        f"/api/plugins/fleet/v1/assets/{created['id']}/events"
    ).json()["items"]
    status_events = [
        item for item in history
        if item["event_type"] == "stato_operativo_mezzo_modificato"
    ]
    assert [item["details"]["reason"] for item in status_events] == [
        "Tagliando programmato",
        "Trasferimento officina convenzionata",
    ]


def test_manual_operational_status_requires_reason_and_valid_state():
    created = asset()
    missing = client.patch(
        f"{DAMAGE}/vehicles/{created['id']}/operational-status",
        json={
            "status": "indisponibile",
            "reason": "",
            "origin": "vehicle_library",
        },
    )
    assert missing.status_code == 422
    invalid = client.patch(
        f"{DAMAGE}/vehicles/{created['id']}/operational-status",
        json={
            "status": "inventato",
            "reason": "Test",
            "origin": "vehicle_library",
        },
    )
    assert invalid.status_code == 422


def test_manual_override_of_open_damage_case_is_explicit_and_append_only():
    case, _ = create_from_anomaly()
    endpoint = f"{DAMAGE}/vehicles/{case['vehicle_id']}/operational-status"
    conflict = client.patch(endpoint, json={
        "status": "disponibile",
        "reason": "Collaudo interno completato",
        "origin": "vehicle_library",
    })
    assert conflict.status_code == 409
    overridden = client.patch(endpoint, json={
        "status": "disponibile",
        "reason": "Collaudo interno completato",
        "origin": "vehicle_library",
        "override_restriction": True,
    })
    assert overridden.status_code == 200
    assert overridden.json()["asset"]["availability"] == "disponibile"
    assert overridden.json()["linked_damage_case"]["case_number"] == case["case_number"]
    damage_events = client.get(
        f"{DAMAGE}/damage-cases/{case['id']}/events"
    ).json()["items"]
    assert damage_events[-1]["event_type"] == "stato_operativo_mezzo_modificato"
    assert damage_events[-1]["note"].startswith("vehicle_library.")

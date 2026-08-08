from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.damage.application.driver_suggestion_resolver import (
    resolve_driver_suggestion,
)
from app.plugins.fleet.damage.domain.driver_suggestion import (
    DriverSuggestionStatus,
)
from app.plugins.workforce.application.driver_identity_resolver import (
    resolve_driver_identity,
)
from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolutionStatus,
)


client = TestClient(app)
FLEET = "/api/plugins/fleet/v1"
JOURNAL = f"{FLEET}/journal"
CONTROL_ROOM = "/api/fleet/journal-control-room"
ORGANIZATION_ID = "test-organization"
NOW = "2026-08-08T10:00:00+00:00"


def _member(
    organization_id: str,
    external_identifier: str,
    display_name: str,
) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'shared-link-test', ?, ?)
            """,
            (
                organization_id,
                external_identifier,
                display_name,
                NOW,
                NOW,
            ),
        ).lastrowid)


def _asset(plate: str = "SG001AA") -> int:
    response = client.post(f"{FLEET}/assets", json={
        "external_identifier": f"SHARED-{plate}",
        "plate": plate,
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    })
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _shared_access() -> str:
    response = client.post(f"{CONTROL_ROOM}/shared-access", json={})
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


def _shared_session(
    access_token: str,
    *,
    name: str = "Alban",
    surname: str = "Beqiraj",
    plate: str = "SG001AA",
) -> dict[str, object]:
    response = client.post(f"{JOURNAL}/sessions/shared", json={
        "driver_name": name,
        "driver_surname": surname,
        "vehicle_plate": plate,
        "procedure_type": "check_out",
        "access_token": access_token,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _stored_session(session_id: str):
    with db_session() as conn:
        return conn.execute(
            "SELECT * FROM journal_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()


def _completion_payload() -> dict[str, object]:
    return {
        "odometer_km": 1234,
        "fuel_percentage": 75,
        "anomaly_present": False,
        "equipment": [
            {"code": "telepass", "status": "present"},
            {"code": "phone", "status": "present"},
            {"code": "keys", "status": "present"},
            {"code": "fuel_card", "status": "present"},
        ],
        "client_submission_id": "shared-canonical-identity",
        "timezone": "Europe/Rome",
    }


def test_shared_link_persists_canonical_identifier_and_keeps_visual_name():
    member_id = _member(
        ORGANIZATION_ID,
        "source-67c5d028b9c784bf",
        "Alban Beqiraj",
    )
    _asset()
    created = _shared_session(_shared_access())

    stored = _stored_session(str(created["session_id"]))
    assert stored["declared_driver_identifier"] == "source-67c5d028b9c784bf"
    assert stored["driver_name"] == "Alban"
    assert stored["driver_surname"] == "Beqiraj"
    resolution = resolve_driver_identity(
        organization_id=ORGANIZATION_ID,
        driver_identifier=stored["declared_driver_identifier"],
        source="journal",
    )
    assert resolution.status is DriverIdentityResolutionStatus.MATCH
    assert resolution.workforce_member_id == member_id


def test_shared_link_resolution_is_strictly_organization_scoped():
    _member("other-organization", "OTHER-001", "Alban Beqiraj")
    _asset()
    created = _shared_session(_shared_access())

    stored = _stored_session(str(created["session_id"]))
    assert stored["declared_driver_identifier"] == "Alban Beqiraj"


def test_unresolved_or_inexact_name_keeps_legacy_value_without_creating_member():
    _member(ORGANIZATION_ID, "DRV-MARIO", "Mario Rossi")
    _asset()
    with db_session() as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM workforce_members"
        ).fetchone()[0]

    created = _shared_session(
        _shared_access(),
        name="Maria",
        surname="Rossi",
    )

    stored = _stored_session(str(created["session_id"]))
    with db_session() as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM workforce_members"
        ).fetchone()[0]
    assert stored["declared_driver_identifier"] == "Maria Rossi"
    assert after == before


def test_ambiguous_exact_name_does_not_choose_a_workforce_member():
    _member(ORGANIZATION_ID, "DRV-FIRST", "Mario Rossi")
    _member(ORGANIZATION_ID, "DRV-SECOND", "Mario Rossi")
    _asset()
    created = _shared_session(
        _shared_access(),
        name="Mario",
        surname="Rossi",
    )

    stored = _stored_session(str(created["session_id"]))
    assert stored["declared_driver_identifier"] == "Mario Rossi"


def test_completed_shared_movement_is_resolved_by_journal_suggestion():
    member_id = _member(
        ORGANIZATION_ID,
        "source-67c5d028b9c784bf",
        "Alban Beqiraj",
    )
    vehicle_id = _asset()
    created = _shared_session(_shared_access())
    response = client.post(
        f"{JOURNAL}/sessions/{created['session_id']}/complete",
        headers={"X-Journal-Token": str(created["token"])},
        json=_completion_payload(),
    )
    assert response.status_code == 200, response.text

    stored = _stored_session(str(created["session_id"]))
    with db_session() as conn:
        movement = conn.execute(
            "SELECT * FROM asset_movements WHERE session_id = ?",
            (created["session_id"],),
        ).fetchone()
    assert movement["declared_driver_identifier"] == "source-67c5d028b9c784bf"
    identity = resolve_driver_identity(
        organization_id=ORGANIZATION_ID,
        driver_identifier=movement["declared_driver_identifier"],
        source="journal",
    )
    assert identity.status is DriverIdentityResolutionStatus.MATCH
    suggestion = resolve_driver_suggestion(
        organization_id=ORGANIZATION_ID,
        vehicle_id=vehicle_id,
        operational_date=stored["operational_date"],
    )
    assert suggestion.status is DriverSuggestionStatus.MATCH
    assert suggestion.source == "journal"
    assert suggestion.workforce_member_id == member_id
    api_response = client.get(
        "/api/fleet/damage-cases/driver-suggestion",
        params={
            "vehicle_id": vehicle_id,
            "operational_date": stored["operational_date"],
        },
    )
    assert api_response.status_code == 200, api_response.text
    assert api_response.json()["status"] == "MATCH"
    assert api_response.json()["source"] == "journal"
    assert api_response.json()["driver"]["workforce_member_id"] == member_id

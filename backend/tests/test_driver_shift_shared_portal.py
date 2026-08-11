from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from tests.test_driver_shift_distribution import (
    BASE,
    ORG,
    _member,
    _planning,
    _scenario,
    _shift,
    _token,
)


def _distribution(client: TestClient, planning_id: int) -> dict:
    response = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution")
    assert response.status_code == 200
    return response.json()


def _portal_token(portal: dict) -> str:
    return portal["access_url"].split("#token=", 1)[1]


def _validate(public: TestClient, token: str):
    return public.post(
        "/api/public/driver-shifts/access/validate", json={"token": token},
    )


def test_prepare_portal_is_idempotent_and_only_hash_is_persisted():
    planning_id, _ = _scenario(1)
    client = TestClient(app)
    distribution = _distribution(client, planning_id)
    distribution_id = distribution["distribution"]["id"]

    first = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal")
    second = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal")
    fetched = client.get(f"{BASE}/driver-shift-distributions/{distribution_id}/portal")

    assert first.status_code == second.status_code == fetched.status_code == 200
    assert first.json()["id"] == second.json()["id"] == fetched.json()["id"]
    assert first.json()["access_url"] == second.json()["access_url"] == fetched.json()["access_url"]
    token = _portal_token(first.json())
    assert len(token) > 80
    assert token.split(".", 1)[0] != str(distribution_id)
    assert ORG not in token
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM driver_shift_distribution_portals WHERE distribution_id=?",
            (distribution_id,),
        ).fetchall()
        assert len(rows) == 1
        assert token not in rows[0]["token_hash"]
        assert len(rows[0]["token_hash"]) == 64


def test_portal_is_organization_scoped_and_public_response_has_no_driver_data():
    planning_id, _ = _scenario(1)
    client = TestClient(app)
    distribution = _distribution(client, planning_id)
    distribution_id = distribution["distribution"]["id"]
    portal = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal").json()
    token = _portal_token(portal)

    other_member = _member("OTHER-PORTAL", "Other Driver", "other-organization")
    other_planning = _planning(organization_id="other-organization")
    _shift(other_planning, other_member, "2026-08-17", organization_id="other-organization")
    with db_session() as conn:
        other_distribution = conn.execute(
            """INSERT INTO driver_shift_distributions (
                   organization_id, driver_shift_planning_id, planning_version,
                   period_start, period_end, status, created_at, created_by, updated_at
               ) VALUES ('other-organization', ?, 1, '2026-08-17', '2026-08-23',
                         'READY', '2026-08-11T09:00:00Z', 'other@test',
                         '2026-08-11T09:00:00Z')""",
            (other_planning,),
        ).lastrowid
    assert client.post(f"{BASE}/driver-shift-distributions/{other_distribution}/portal").status_code == 404

    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    response = _validate(public, token)
    assert response.status_code == 200
    assert response.json() == {"available": True}
    serialized = response.text.casefold()
    for forbidden in ("driver", "recipient", "organization", "station", "shift"):
        assert forbidden not in serialized


def test_invalid_revoked_expired_and_regenerated_portals_use_safe_not_found():
    planning_id, _ = _scenario(1)
    client = TestClient(app)
    distribution = _distribution(client, planning_id)
    distribution_id = distribution["distribution"]["id"]
    portal = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal").json()
    old_token = _portal_token(portal)
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})

    invalid = _validate(public, "invalid-token")
    assert invalid.status_code == 404
    assert "revoked" not in invalid.text.casefold() and "expired" not in invalid.text.casefold()

    revoked = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"
    assert revoked.json()["access_url"] is None
    assert _validate(public, old_token).status_code == 404

    regenerated = client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/portal/regenerate"
    )
    assert regenerated.status_code == 200
    new_token = _portal_token(regenerated.json())
    assert new_token != old_token
    assert _validate(public, old_token).status_code == 404
    assert _validate(public, new_token).status_code == 200

    with db_session() as conn:
        conn.execute(
            """UPDATE driver_shift_distribution_portals
               SET expires_at='2020-01-01T00:00:00Z' WHERE distribution_id=?""",
            (distribution_id,),
        )
    expired = _validate(public, new_token)
    assert expired.status_code == 404
    assert "expired" not in expired.text.casefold()
    current = client.get(f"{BASE}/driver-shift-distributions/{distribution_id}/portal")
    assert current.json()["status"] == "EXPIRED"
    assert current.json()["access_url"] is None


def test_superseded_distribution_invalidates_shared_portal_but_not_personal_feature():
    first_planning, members = _scenario(1)
    client = TestClient(app)
    first_distribution = _distribution(client, first_planning)
    distribution_id = first_distribution["distribution"]["id"]
    shared = client.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal").json()
    shared_token = _portal_token(shared)
    personal_token = _token(client, first_distribution)

    with db_session() as conn:
        conn.execute(
            "UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?",
            (first_planning,),
        )
    second_planning = _planning(version=2, label="Revisione 2")
    _shift(second_planning, members[0], "2026-08-19", version=2)
    _distribution(client, second_planning)

    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    assert _validate(public, shared_token).status_code == 404
    assert public.get(f"/api/public/driver-shifts/{personal_token}").status_code == 404
    with db_session() as conn:
        portal = conn.execute(
            "SELECT status FROM driver_shift_distribution_portals WHERE id=?",
            (shared["id"],),
        ).fetchone()
        assert portal["status"] == "REVOKED"

    current_distribution = _distribution(client, second_planning)
    current_personal = _token(client, current_distribution)
    assert public.get(f"/api/public/driver-shifts/{current_personal}").status_code == 200


def test_public_landing_is_private_and_contains_no_operational_metadata():
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    response = public.get("/app/driver-shifts/access/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "I tuoi turni" in response.text
    assert "Accedi al portale condiviso della tua organizzazione." in response.text
    for forbidden in ("Mario Rossi", "recipient", "organization_id", "station"):
        assert forbidden not in response.text

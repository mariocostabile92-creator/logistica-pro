from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_credentials_service
from app.plugins.workforce.application import driver_shift_driver_session_service
from app.workspace.reset_service import reset_workspace
from tests.test_driver_shift_distribution import BASE, ORG, _member, _scenario


def _setup(driver_count: int = 2):
    planning_id, members = _scenario(driver_count)
    admin = TestClient(app)
    distribution = admin.post(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution"
    ).json()
    distribution_id = distribution["distribution"]["id"]
    credentials = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/credentials/prepare"
    ).json()["initial_credentials"]
    portal = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/portal"
    ).json()
    token = portal["access_url"].split("#token=", 1)[1]
    return admin, planning_id, members, distribution, credentials, portal, token


def _public() -> TestClient:
    return TestClient(app, headers={"X-Test-Auth-Harness": ""})


def _login(client: TestClient, token: str, credential: dict, *, remember=False):
    return client.post(
        "/api/public/driver-shifts/portal/login",
        json={
            "portal_token": token,
            "access_code": credential["access_code"],
            "pin": credential["initial_pin"],
            "remember_device": remember,
        },
    )


def test_login_creates_private_session_and_me_contains_only_safe_driver_data():
    _, _, _, distribution, credentials, _, token = _setup(1)
    public = _public()
    response = _login(public, token, credentials[0])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    cookie = response.headers["set-cookie"]
    assert "driver_shift_session=" in cookie
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/public/driver-shifts" in cookie
    body = response.json()
    assert body == {
        "authenticated": True,
        "driver_name": credentials[0]["display_name"],
        "period_start": "2026-08-17",
        "period_end": "2026-08-23",
        "access_status": "OPENED",
    }
    me = public.get("/api/public/driver-shifts/me")
    assert me.status_code == 200 and me.json() == body
    serialized = me.text.casefold()
    for forbidden in (
        "organization", "workforce_member", "distribution_id", "portal_id",
        "credential", "access_code", "pin", "session_token", "shift",
    ):
        assert forbidden not in serialized
    with db_session() as conn:
        session = conn.execute("SELECT * FROM driver_shift_driver_sessions").fetchone()
        recipient = conn.execute(
            "SELECT * FROM driver_shift_distribution_recipients WHERE distribution_id=?",
            (distribution["distribution"]["id"],),
        ).fetchone()
    assert session is not None and len(session["session_token_hash"]) == 64
    assert "driver_shift_session=" not in str(session["session_token_hash"])
    assert recipient["first_opened_at"] is not None
    assert recipient["last_opened_at"] is not None
    assert recipient["access_status"] == "OPENED"


def test_two_drivers_using_same_portal_receive_strictly_isolated_sessions():
    _, _, _, _, credentials, _, token = _setup(2)
    driver_a = _public()
    driver_b = _public()
    assert _login(driver_a, token, credentials[0]).status_code == 200
    assert _login(driver_b, token, credentials[1]).status_code == 200
    name_a = driver_a.get("/api/public/driver-shifts/me").json()["driver_name"]
    name_b = driver_b.get("/api/public/driver-shifts/me").json()["driver_name"]
    assert name_a == credentials[0]["display_name"]
    assert name_b == credentials[1]["display_name"]
    assert name_a != name_b
    with db_session() as conn:
        rows = conn.execute(
            "SELECT workforce_member_id, session_token_hash FROM driver_shift_driver_sessions"
        ).fetchall()
    assert len(rows) == 2
    assert len({row["workforce_member_id"] for row in rows}) == 2
    assert len({row["session_token_hash"] for row in rows}) == 2


def test_invalid_code_pin_non_recipient_and_cross_organization_are_indistinguishable():
    _, _, _, _, credentials, _, token = _setup(1)
    public = _public()
    invalid_payloads = [
        {"access_code": "AAAAAAAA", "pin": "000000"},
        {"access_code": "CODICÈÈÈ", "pin": "000000"},
        {"access_code": credentials[0]["access_code"], "pin": "000000"},
    ]

    outsider = _member("NOT-A-RECIPIENT", "Not Recipient")
    outsider_code = "ZZZZZZZZ"
    outsider_pin = "991122"
    with db_session() as conn:
        conn.execute(
            """INSERT INTO driver_shift_driver_credentials (
                   organization_id, workforce_member_id, credential_status,
                   access_code_hash, pin_hash, generation, created_at, updated_at,
                   reset_at, revoked_at
               ) VALUES (?, ?, 'ACTIVE', ?, ?, 1, ?, ?, NULL, NULL)""",
            (
                ORG, outsider,
                driver_shift_credentials_service.access_code_fingerprint(outsider_code),
                driver_shift_credentials_service._hash_pin(outsider_pin),
                "2026-08-11T09:00:00+00:00", "2026-08-11T09:00:00+00:00",
            ),
        )
    invalid_payloads.append({"access_code": outsider_code, "pin": outsider_pin})

    for item in invalid_payloads:
        response = public.post(
            "/api/public/driver-shifts/portal/login",
            json={"portal_token": token, "remember_device": False, **item},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Dati di accesso non validi."}

    assert public.get("/api/public/driver-shifts/me").status_code == 401
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM driver_shift_driver_sessions").fetchone()["total"] == 0


def test_session_is_invalidated_by_credential_reset_and_revoke():
    admin, _, members, _, credentials, _, token = _setup(1)
    first = _public()
    assert _login(first, token, credentials[0]).status_code == 200
    reset = admin.post(f"{BASE}/credentials/{members[0]}/reset")
    assert reset.status_code == 200
    assert first.get("/api/public/driver-shifts/me").status_code == 401

    second = _public()
    new_credential = {
        "access_code": credentials[0]["access_code"],
        "initial_pin": reset.json()["initial_pin"],
    }
    assert _login(second, token, new_credential).status_code == 200
    assert admin.post(f"{BASE}/credentials/{members[0]}/revoke").status_code == 200
    assert second.get("/api/public/driver-shifts/me").status_code == 401


def test_portal_revoke_regenerate_and_distribution_supersede_invalidate_sessions():
    admin, planning_id, _, distribution, credentials, _, token = _setup(1)
    distribution_id = distribution["distribution"]["id"]
    public = _public()
    assert _login(public, token, credentials[0]).status_code == 200
    admin.post(f"{BASE}/driver-shift-distributions/{distribution_id}/portal/revoke")
    assert public.get("/api/public/driver-shifts/me").status_code == 401

    regenerated = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/portal/regenerate"
    ).json()
    new_token = regenerated["access_url"].split("#token=", 1)[1]
    again = _public()
    assert _login(again, new_token, credentials[0]).status_code == 200
    with db_session() as conn:
        conn.execute(
            "UPDATE driver_shift_distributions SET status='SUPERSEDED' WHERE id=?",
            (distribution_id,),
        )
        conn.execute(
            "UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?",
            (planning_id,),
        )
    assert again.get("/api/public/driver-shifts/me").status_code == 401


def test_logout_is_idempotent_and_revokes_only_current_session():
    _, _, _, _, credentials, _, token = _setup(2)
    a, b = _public(), _public()
    _login(a, token, credentials[0])
    _login(b, token, credentials[1])
    first = a.post("/api/public/driver-shifts/logout")
    second = a.post("/api/public/driver-shifts/logout")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"authenticated": False}
    assert a.get("/api/public/driver-shifts/me").status_code == 401
    assert b.get("/api/public/driver-shifts/me").status_code == 200


def test_rate_limit_is_persistent_generic_and_never_stores_raw_input():
    _, _, _, _, credentials, _, token = _setup(1)
    public = _public()
    for _ in range(driver_shift_driver_session_service.MAX_CODE_FAILURES):
        response = public.post(
            "/api/public/driver-shifts/portal/login",
            json={
                "portal_token": token,
                "access_code": credentials[0]["access_code"],
                "pin": "000000",
                "remember_device": False,
            },
        )
        assert response.status_code == 401
    locked = _login(public, token, credentials[0])
    assert locked.status_code == 429
    assert locked.json() == {"detail": "Dati di accesso non validi."}
    assert locked.headers["retry-after"] == "900"
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM driver_shift_login_attempts").fetchall()
    serialized = str([{key: row[key] for key in row.keys()} for row in rows])
    assert credentials[0]["access_code"] not in serialized
    assert credentials[0]["initial_pin"] not in serialized


def test_session_expiry_cookie_policy_and_workspace_reset_are_safe(monkeypatch):
    _, _, _, _, credentials, portal, token = _setup(1)
    transient = _public()
    remembered = _public()
    first = _login(transient, token, credentials[0], remember=False)
    second = _login(remembered, token, credentials[0], remember=True)
    assert "expires=" not in first.headers["set-cookie"].casefold()
    assert "expires=" in second.headers["set-cookie"].casefold()
    assert driver_shift_driver_session_service.cookie_options(
        remember_device=True,
        expires_at=datetime.now(timezone.utc),
    )["secure"] is False
    monkeypatch.setattr(
        driver_shift_driver_session_service,
        "SETTINGS",
        SimpleNamespace(production=True, secret_key="production-test-secret"),
    )
    assert driver_shift_driver_session_service.cookie_options(
        remember_device=True,
        expires_at=datetime.now(timezone.utc),
    )["secure"] is True
    with db_session() as conn:
        session_expiry = conn.execute(
            "SELECT MAX(expires_at) value FROM driver_shift_driver_sessions"
        ).fetchone()["value"]
    assert session_expiry <= portal["expires_at"]

    token_context = bind_organization(ORG)
    try:
        result = reset_workspace(actor="admin@test")
    finally:
        reset_organization(token_context)
    assert result.removed_counts.driver_shift_driver_sessions == 2
    assert result.removed_counts.driver_shift_login_attempts == 0
    assert remembered.get("/api/public/driver-shifts/me").status_code == 401


def test_cross_site_mutations_are_rejected_and_personal_links_still_work():
    admin, _, _, distribution, credentials, _, token = _setup(1)
    public = _public()
    rejected = public.post(
        "/api/public/driver-shifts/portal/login",
        headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
        json={
            "portal_token": token,
            "access_code": credentials[0]["access_code"],
            "pin": credentials[0]["initial_pin"],
            "remember_device": False,
        },
    )
    assert rejected.status_code == 403
    recipient = distribution["recipients"][0]
    link = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution['distribution']['id']}"
        f"/recipients/{recipient['id']}/access-link"
    ).json()["access_url"]
    personal_token = link.split("#token=", 1)[1]
    personal = public.get(f"/api/public/driver-shifts/{personal_token}")
    assert personal.status_code == 200
    assert personal.json()["driver_name"] == credentials[0]["display_name"]

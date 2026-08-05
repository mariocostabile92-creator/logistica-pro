from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.database import db_session
from app.main import app


client = TestClient(app)
ENFORCE = {"X-Auth-Enforce": "1"}


def user(email: str, role: Role, password: str = "Password-sicura-123"):
    create_user(email, hash_password(password), role, "QA Operations")
    return password


def sign_in(email: str, password: str, remember: bool = False):
    return client.post("/api/auth/login", json={
        "email": email, "password": password, "remember_me": remember,
    }, headers=ENFORCE)


def test_admin_area_redirects_and_api_returns_401_without_session():
    response = client.get("/app/", headers=ENFORCE, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/bootstrap.html"
    assert client.get("/api/fleet/vision", headers=ENFORCE).status_code == 401
    assert client.get("/app/login.html", headers=ENFORCE).status_code == 200


def test_organization_registration_is_public_before_first_login():
    response = client.post(
        "/api/auth/register",
        json={
            "organization": {
                "name": "QA Company",
                "primary_station": "DLO2",
                "timezone": "Europe/Rome",
                "language": "it",
            },
            "administrator": {
                "first_name": "Mario",
                "last_name": "Costabile",
                "email": "new-company@example.test",
                "password": "Password-sicura-123",
                "password_confirmation": "Password-sicura-123",
            },
        },
        headers=ENFORCE,
    )

    assert response.status_code == 201
    assert response.json()["user"]["organization"]["name"] == "QA Company"
    assert "operations_session" in response.headers["set-cookie"]


def test_login_session_remember_and_logout_use_secure_server_session():
    password = user("admin@example.test", Role.ADMINISTRATOR)
    login = sign_in("admin@example.test", password, True)
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "administrator"
    assert login.json()["user"]["organization"]["name"] == "QA Operations"
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "operations_session" in client.cookies
    session = client.get("/api/auth/session", headers=ENFORCE)
    assert session.status_code == 200
    assert "users:manage" in session.json()["user"]["permissions"]
    assert client.post("/api/auth/logout", headers=ENFORCE).status_code == 204
    assert client.get("/api/auth/session", headers=ENFORCE).status_code == 401


def test_invalid_credentials_and_expired_session_return_401_not_500():
    password = user("fleet@example.test", Role.FLEET_MANAGER)
    assert sign_in("fleet@example.test", "password-errata").status_code == 401
    assert sign_in("fleet@example.test", password).status_code == 200
    with db_session() as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at=?",
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(),),
        )
    assert client.get("/api/fleet/vision", headers=ENFORCE).status_code == 401
    expired = client.get("/api/auth/session", headers=ENFORCE)
    assert expired.status_code == 401
    assert "operations_session=" in expired.headers["set-cookie"]
    with db_session() as conn:
        assert conn.execute(
            "SELECT revoked_at FROM auth_sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()["revoked_at"] is not None


def test_roles_exist_and_viewer_write_is_forbidden():
    assert {role.value for role in Role} == {
        "operations_manager", "fleet_manager", "dispatcher", "viewer", "administrator",
    }
    password = user("viewer@example.test", Role.VIEWER)
    assert sign_in("viewer@example.test", password).status_code == 200
    assert client.get("/api/fleet/vision", headers=ENFORCE).status_code == 200
    denied = client.post(
        "/api/fleet/journal-control-room/shared-access",
        json={"regenerate": False}, headers=ENFORCE,
    )
    assert denied.status_code == 403


def test_fleet_role_can_write_and_audit_is_persisted():
    password = user("manager@example.test", Role.FLEET_MANAGER)
    assert sign_in("manager@example.test", password).status_code == 200
    created = client.post(
        "/api/fleet/journal-control-room/shared-access",
        json={"regenerate": False}, headers=ENFORCE,
    )
    assert created.status_code == 201
    with db_session() as conn:
        audit = conn.execute("SELECT * FROM admin_audit_events").fetchone()
    assert audit["user_id"]
    assert audit["action"] == "POST"
    assert audit["target"] == "/api/fleet/journal-control-room/shared-access"


def test_driver_journal_and_shared_link_validation_remain_public():
    assert client.get(
        "/api/plugins/fleet/v1/journal/configuration", headers=ENFORCE,
    ).status_code == 200
    assert client.get(
        "/api/plugins/fleet/v1/assets", headers=ENFORCE,
    ).status_code == 401
    assert client.get("/app/journal/", headers=ENFORCE).status_code == 200
    assert client.get(
        "/api/plugins/fleet/v1/journal/shared-access/unknown", headers=ENFORCE,
    ).status_code in {404, 410}


def test_admin_journal_routes_are_not_exposed_by_the_public_driver_prefix():
    assert client.get(
        "/api/plugins/fleet/v1/journal/vehicles/1/history", headers=ENFORCE,
    ).status_code == 401
    assert client.get(
        "/api/plugins/fleet/v1/journal/not-a-public-route", headers=ENFORCE,
    ).status_code == 401
    assert client.get("/api/fleet/journal-integrity", headers=ENFORCE).status_code == 401


def test_backend_permissions_separate_planning_and_fleet_mutations():
    dispatcher_password = user("dispatcher@example.test", Role.DISPATCHER)
    assert sign_in("dispatcher@example.test", dispatcher_password).status_code == 200
    assert client.post(
        "/api/fleet/damage-cases", json={}, headers=ENFORCE,
    ).status_code == 403
    assert client.post(
        "/api/planning-operations/forecast", json={}, headers=ENFORCE,
    ).status_code != 403

    fleet_password = user("fleet.permissions@example.test", Role.FLEET_MANAGER)
    assert sign_in("fleet.permissions@example.test", fleet_password).status_code == 200
    assert client.post(
        "/api/planning-operations/forecast", json={}, headers=ENFORCE,
    ).status_code == 403
    assert client.post(
        "/api/fleet/damage-cases", json={}, headers=ENFORCE,
    ).status_code != 403


def test_pwa_and_unhashed_modules_require_revalidation():
    password = user("pwa@example.test", Role.ADMINISTRATOR)
    assert sign_in("pwa@example.test", password).status_code == 200
    for path in (
        "/app/", "/app/sw.js", "/app/manifest.webmanifest",
        "/app/assets/js/app.js", "/app/assets/css/base.css",
    ):
        response = client.get(path, headers=ENFORCE)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
    worker = client.get("/app/sw.js", headers=ENFORCE).text
    assert "registration.unregister" in worker
    assert 'addEventListener("fetch"' not in worker

    versioned = client.get("/app/assets/js/app.js?v=37", headers=ENFORCE)
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
ENFORCE = {"X-Auth-Enforce": "1"}
PASSWORD = "Password-sicura-123"


def bootstrap():
    return client.post("/api/auth/bootstrap", headers=ENFORCE, json={
        "organization": {"name": "Mario Logistics", "primary_station": "Roma",
                         "timezone": "Europe/Rome", "language": "it"},
        "administrator": {"first_name": "Mario", "last_name": "Rossi",
                          "email": "mario@example.test", "password": PASSWORD,
                          "password_confirmation": PASSWORD},
    })


def create_user(role="fleet_manager", email="fleet@example.test"):
    return client.post("/api/organization/users", headers=ENFORCE, json={
        "first_name": "Fleet", "last_name": "Manager", "email": email,
        "role": role, "temporary_password": PASSWORD, "active": True,
    })


def test_empty_database_requires_one_time_bootstrap_and_creates_session():
    assert client.get("/api/auth/bootstrap/status", headers=ENFORCE).json() == {"required": True}
    redirect = client.get("/app/", headers=ENFORCE, follow_redirects=False)
    assert redirect.headers["location"] == "/app/bootstrap.html"
    created = bootstrap()
    assert created.status_code == 201
    assert created.json()["user"]["role"] == "administrator"
    assert created.json()["user"]["organization"]["name"] == "Mario Logistics"
    assert client.get("/api/auth/session", headers=ENFORCE).status_code == 200
    assert client.get("/api/auth/bootstrap/status", headers=ENFORCE).json() == {"required": False}
    assert bootstrap().status_code == 409
    unavailable = client.get("/app/bootstrap.html", headers=ENFORCE, follow_redirects=False)
    assert unavailable.headers["location"] == "/app/login.html"


def test_administrator_creates_users_in_session_organization_and_viewer_is_forbidden():
    assert bootstrap().status_code == 201
    for role in ("fleet_manager", "dispatcher", "viewer"):
        assert create_user(role, f"{role}@example.test").status_code == 201
    organization = client.get("/api/organization", headers=ENFORCE).json()
    users = client.get("/api/organization/users", headers=ENFORCE).json()["items"]
    assert organization["primary_station"] == "Roma"
    assert {item["role"] for item in users} == {
        "administrator", "fleet_manager", "dispatcher", "viewer",
    }
    viewer = TestClient(app)
    assert viewer.post("/api/auth/login", headers=ENFORCE, json={
        "email": "viewer@example.test", "password": PASSWORD, "remember_me": False,
    }).status_code == 200
    assert viewer.get("/api/organization/users", headers=ENFORCE).status_code == 403


def test_role_status_and_password_management_are_audited():
    assert bootstrap().status_code == 201
    created = create_user()
    user_id = created.json()["id"]
    changed = client.patch(f"/api/organization/users/{user_id}", headers=ENFORCE, json={
        "first_name": "Fleet", "last_name": "Manager", "role": "dispatcher", "active": False,
    })
    assert changed.status_code == 200
    assert changed.json()["role"] == "dispatcher" and not changed.json()["active"]
    assert client.patch(f"/api/organization/users/{user_id}", headers=ENFORCE, json={
        "first_name": "Fleet", "last_name": "Manager", "role": "dispatcher", "active": True,
    }).status_code == 200
    assert client.post(f"/api/organization/users/{user_id}/password", headers=ENFORCE,
                       json={"password": "Nuova-password-456"}).status_code == 204


def test_last_administrator_cannot_be_deactivated_or_demoted():
    assert bootstrap().status_code == 201
    admin = client.get("/api/organization/users", headers=ENFORCE).json()["items"][0]
    for role, active in (("viewer", True), ("administrator", False)):
        response = client.patch(f"/api/organization/users/{admin['id']}", headers=ENFORCE, json={
            "first_name": "Mario", "last_name": "Rossi", "role": role, "active": active,
        })
        assert response.status_code == 409
        assert "ultimo Administrator" in response.json()["detail"]

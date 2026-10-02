from importlib.metadata import requires, version
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from packaging.requirements import Requirement
from packaging.version import Version
from starlette.datastructures import URL
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from app.auth.domain import Role
from app.auth.middleware import public_path
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.config import load_settings
from app.main import app


PRIVATE = "/api/planning/confirmation/history"
MALFORMED_HOST = "testserver/api/health?ignored="
HOSTS = (
    "testserver",
    MALFORMED_HOST,
    "testserver/api/health#ignored=",
    "testserver:80/api/health?ignored=",
    "testserver/app/assets/?ignored=",
    "testserver/api/auth/session?ignored=",
    "testserver/api/plugins/fleet/v1/journal/configuration?ignored=",
    "testserver?ignored=",
    "testserver#ignored=",
)
ENFORCE = {"X-Auth-Enforce": "1"}


@pytest.mark.parametrize("host", HOSTS)
def test_private_route_cannot_become_public_through_host(host):
    client = TestClient(app, headers=ENFORCE)
    assert client.get(PRIVATE, headers={"Host": host}).status_code == 401


@pytest.mark.parametrize("root_path", ["", "/proxy"])
def test_classification_uses_router_path_even_if_reconstructed_url_is_poisoned(root_path):
    request = Request({
        "type": "http", "method": "GET", "scheme": "http",
        "path": root_path + PRIVATE, "root_path": root_path,
        "query_string": b"", "server": ("testserver", 80),
        "headers": [(b"host", MALFORMED_HOST.encode())],
    })
    # Keep the application regression independent of Starlette's URL repair.
    request._url = URL("http://testserver/api/health")
    assert public_path(request) is False


@pytest.mark.parametrize("root_path", ["", "/proxy"])
@pytest.mark.parametrize("host", ["testserver", MALFORMED_HOST])
def test_public_routes_and_private_routes_agree_with_routing(root_path, host):
    client = TestClient(app, root_path=root_path, headers={**ENFORCE, "Host": host})
    assert client.get(root_path + "/api/health").status_code == 200
    assert client.get(root_path + "/api/plugins/fleet/v1/journal/configuration").status_code == 200
    assert client.get(root_path + "/api/plugins/fleet/v1/journal/vehicles/1/history").status_code == 401
    assert client.get(root_path + PRIVATE).status_code == 401
    assert client.get(root_path + "/api/configuration/v1/versions").status_code == 401


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-Host": MALFORMED_HOST},
    {"Forwarded": 'host="testserver/api/health?ignored=";proto=https'},
    {"Host": MALFORMED_HOST, "X-Forwarded-Host": "testserver"},
])
def test_forwarding_headers_do_not_change_auth_classification(headers):
    client = TestClient(app, headers=ENFORCE)
    assert client.get(PRIVATE, headers=headers).status_code == 401


def test_url_encoding_and_query_string_do_not_change_private_route_auth():
    client = TestClient(app, headers=ENFORCE)
    for path in ("/api/%70lanning/confirmation/history", PRIVATE + "?next=/api/health"):
        assert client.get(path, headers={"Host": MALFORMED_HOST}).status_code == 401


def _signed_in(role):
    email = f"host-security-{role.value}@example.test"
    password = "Password-sicura-123"
    create_user(email, hash_password(password), role, "Host Security")
    client = TestClient(app, headers=ENFORCE)
    assert client.post("/api/auth/login", json={
        "email": email, "password": password, "remember_me": False,
    }).status_code == 200
    return client


def test_valid_session_remains_valid_and_logout_still_requires_session_semantics():
    client = _signed_in(Role.ADMINISTRATOR)
    for host in ("testserver", MALFORMED_HOST):
        assert client.get(PRIVATE, headers={"Host": host}).status_code == 200
        assert client.get("/api/auth/session", headers={"Host": host}).status_code == 200
    assert client.post("/api/auth/logout", headers={"Host": MALFORMED_HOST}).status_code == 204
    assert client.get(PRIVATE, headers={"Host": MALFORMED_HOST}).status_code == 401


def test_malformed_host_does_not_bypass_role_permissions():
    client = _signed_in(Role.VIEWER)
    for host in ("testserver", MALFORMED_HOST):
        assert client.post("/api/planning/confirmation/confirm", json={}, headers={"Host": host}).status_code == 403


def test_trusted_hosts_remains_an_additional_independent_boundary():
    settings = load_settings({"APP_ENV": "test", "TRUSTED_HOSTS": "testserver"})
    guarded_app = TrustedHostMiddleware(app, allowed_hosts=list(settings.trusted_hosts))
    # Share app state for the suite's TestClient wrapper; ENFORCE disables its bypass.
    guarded_app.state = app.state
    client = TestClient(guarded_app, headers=ENFORCE)
    assert client.get("/api/health", headers={"Host": "testserver"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
    assert client.get(PRIVATE, headers={"Host": MALFORMED_HOST}).status_code == 400
    assert client.get(PRIVATE, headers={"Host": "testserver"}).status_code == 401
    assert load_settings({"APP_ENV": "test"}).trusted_hosts == ("*",)


def test_starlette_security_patch_is_pinned_and_compatible_with_fastapi():
    installed = Version(version("starlette"))
    assert installed >= Version("1.0.1")
    runtime_requirements = Path(__file__).parents[1] / "requirements.txt"
    pin = next(
        Requirement(line) for line in runtime_requirements.read_text().splitlines()
        if line.startswith("starlette")
    )
    assert installed in pin.specifier
    dependency = next(Requirement(line) for line in requires("fastapi") if Requirement(line).name == "starlette")
    assert installed in dependency.specifier


def test_patched_starlette_does_not_reconstruct_public_path_from_invalid_host():
    request = Request({
        "type": "http", "method": "GET", "scheme": "http", "path": PRIVATE,
        "query_string": b"", "server": ("testserver", 80),
        "headers": [(b"host", MALFORMED_HOST.encode())],
    })
    assert request.url.path == PRIVATE

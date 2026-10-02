import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.dependencies.organization_scope import authenticated_organization_id
from app.core.configuration.models import ConfigurationScope
from app.core.configuration.service import create_configuration_version
from app.core.database import db_session
from app.domain.planning_drafts import PlanningDraftNotFoundError
from app.main import app
from app.repositories.planning_draft_repository import SqlPlanningDraftRepository


CONFIG = "/api/configuration/v1"
DRAFTS = "/api/planning/drafts"
DAY = "2026-08-10"


def _registered_client(label):
    client = TestClient(app, headers={"X-Auth-Enforce": "1"})
    response = client.post("/api/auth/register", json={
        "organization": {"name": f"Tenant {label}", "timezone": "Europe/Rome", "language": "it"},
        "administrator": {
            "first_name": "Tenant", "last_name": label,
            "email": f"tenant-{label}@example.test",
            "password": "Password-sicura-123", "password_confirmation": "Password-sicura-123",
        },
    })
    assert response.status_code == 201, response.text
    return client, response.json()["user"]["organization"]["id"]


def _configuration(organization_id, label):
    return {
        "organization_id": organization_id,
        "note": f"private-{label}",
        "sections": [{"key": "nomenclature", "values": [{"key": "asset_label", "value": label}]}],
    }


def _draft(organization_id):
    return {
        "organization_id": organization_id, "operational_unit_id": "unit-one",
        "planning_date": DAY, "name": "Private draft",
    }


@pytest.fixture
def tenants():
    a, org_a = _registered_client("A")
    b, org_b = _registered_client("B")
    assert a.post(f"{CONFIG}/versions", json=_configuration(org_a, "A")).status_code == 201
    assert b.post(f"{CONFIG}/versions", json=_configuration(org_b, "B")).status_code == 201
    created = b.post(DRAFTS, json=_draft(org_b))
    assert created.status_code == 201
    draft_id = created.json()["draft"]["draft_id"]
    assert b.post(f"{DRAFTS}/{draft_id}/save", json={"expected_version": 1}).status_code == 200
    yield a, org_a, b, org_b, draft_id
    a.close()
    b.close()


@pytest.mark.parametrize("endpoint", ["current", "versions"])
def test_configuration_reads_require_the_authenticated_organization(tenants, endpoint):
    a, org_a, b, org_b, _ = tenants
    own = a.get(f"{CONFIG}/{endpoint}", params={"organization_id": org_a})
    assert own.status_code == 200
    forbidden = a.get(f"{CONFIG}/{endpoint}", params={
        "organization_id": org_b, "operational_unit_id": "unit-one", "adapter_id": "generic",
    })
    assert forbidden.status_code == 403
    assert "private-B" not in forbidden.text
    assert b.get(f"{CONFIG}/{endpoint}", params={"organization_id": org_b}).status_code == 200


@pytest.mark.parametrize("endpoint", ["validate", "versions"])
def test_configuration_writes_and_validation_reject_other_tenant(tenants, endpoint):
    a, org_a, b, org_b, _ = tenants
    before = b.get(f"{CONFIG}/versions", params={"organization_id": org_b}).json()
    response = a.post(f"{CONFIG}/{endpoint}", json=_configuration(org_b, "overwritten"))
    assert response.status_code == 403
    assert b.get(f"{CONFIG}/versions", params={"organization_id": org_b}).json() == before
    assert a.post(f"{CONFIG}/{endpoint}", json=_configuration(org_a, "own")).status_code == (
        201 if endpoint == "versions" else 200
    )


def test_configuration_default_alias_never_reads_or_writes_stored_default_tenant(tenants):
    a, org_a, _, _, _ = tenants
    create_configuration_version(
        scope=ConfigurationScope(organization_id="default"), raw_sections=[],
        created_by="internal-seed", note="private-default-tenant",
    )
    for params in ({}, {"organization_id": "default"}):
        response = a.get(f"{CONFIG}/current", params=params)
        assert response.status_code == 200
        assert response.json()["metadata"]["requested_scope"]["organization_id"] == org_a
        assert "private-default-tenant" not in response.text
    payload = _configuration("default", "owned-default-alias")
    response = a.post(f"{CONFIG}/versions", json=payload)
    assert response.status_code == 201
    assert response.json()["metadata"]["resolved_scope"]["organization_id"] == org_a
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM configuration_versions WHERE organization_id='default'"
        ).fetchone()["total"] == 1


def test_draft_create_and_current_reject_other_tenant_without_writing(tenants):
    a, org_a, _, org_b, _ = tenants
    with db_session() as conn:
        before = conn.execute("SELECT COUNT(*) AS total FROM planning_drafts").fetchone()["total"]
    assert a.post(DRAFTS, json=_draft(org_b)).status_code == 403
    assert a.get(f"{DRAFTS}/current", params={
        "organization_id": org_b, "operational_unit_id": "unit-one", "planning_date": DAY,
    }).status_code == 403
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) AS total FROM planning_drafts").fetchone()["total"] == before
    response = a.post(DRAFTS, json=_draft(org_a))
    assert response.status_code == 201
    assert response.json()["draft"]["scope"]["organization_id"] == org_a


@pytest.mark.parametrize("operation", ["history", "metadata", "save", "restore", "delete"])
def test_every_draft_id_endpoint_hides_other_tenants_and_preserves_history(tenants, operation):
    a, org_a, b, _, draft_id = tenants
    before = b.get(f"{DRAFTS}/{draft_id}/history").json()
    for target in (draft_id, "does-not-exist"):
        path = f"{DRAFTS}/{target}"
        if operation == "history":
            response = a.get(f"{path}/history", params={"organization_id": org_a})
        elif operation == "metadata":
            response = a.patch(f"{path}/metadata", json={"expected_version": 2, "name": "attacker"})
        elif operation == "delete":
            response = a.delete(path, params={"expected_version": 2})
        else:
            payload = {"expected_version": 2}
            if operation == "restore":
                payload["target_version"] = 1
            response = a.post(f"{path}/{operation}", json=payload)
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["code"] == "PLANNING_DRAFT_NOT_FOUND"
    assert b.get(f"{DRAFTS}/{draft_id}/history").json() == before


@pytest.mark.parametrize("explicit_scope", [False, True])
def test_default_or_omitted_draft_scope_is_session_owned_and_lifecycle_still_works(tenants, explicit_scope):
    a, org_a, _, _, _ = tenants
    payload = _draft("default")
    if not explicit_scope:
        payload.pop("organization_id")
    created = a.post(DRAFTS, json=payload)
    assert created.status_code == 201
    draft = created.json()["draft"]
    assert draft["scope"]["organization_id"] == org_a
    draft_id = draft["draft_id"]
    current = a.get(f"{DRAFTS}/current", params={
        "operational_unit_id": "unit-one", "planning_date": DAY,
    })
    assert current.json()["draft"]["draft_id"] == draft_id
    assert a.patch(f"{DRAFTS}/{draft_id}/metadata", json={"expected_version": 1, "name": "Owned"}).status_code == 200
    assert a.post(f"{DRAFTS}/{draft_id}/save", json={"expected_version": 2}).status_code == 200
    assert a.post(f"{DRAFTS}/{draft_id}/restore", json={"expected_version": 3, "target_version": 1}).status_code == 200
    assert a.delete(f"{DRAFTS}/{draft_id}", params={"expected_version": 4}).status_code == 200
    assert a.get(f"{DRAFTS}/{draft_id}/history").json()["total_versions"] == 5


def test_tenant_bound_repository_filters_ids_snapshots_history_and_updates(tenants):
    _, org_a, _, _, draft_id = tenants
    internal = SqlPlanningDraftRepository()
    foreign = internal.get_by_id(draft_id)
    history = internal.get_history(draft_id)
    scoped = SqlPlanningDraftRepository(organization_id=org_a)
    assert scoped.get_by_id(draft_id) is None
    assert scoped.get_snapshot(draft_id, 1) is None
    hidden = scoped.get_history(draft_id)
    assert hidden.total_changes == hidden.total_versions == 0
    assert hidden.changes == hidden.snapshots == ()
    with pytest.raises(PlanningDraftNotFoundError):
        scoped.get_active(foreign.scope)
    with pytest.raises(PlanningDraftNotFoundError):
        scoped.create(foreign, history.snapshots[0], history.changes[0])
    with pytest.raises(PlanningDraftNotFoundError):
        scoped.replace(foreign, history.snapshots[0], history.changes[0], expected_version=2)
    forged = foreign.model_copy(update={
        "scope": foreign.scope.model_copy(update={"organization_id": org_a}),
    })
    assert scoped.replace(forged, history.snapshots[0], history.changes[0], expected_version=2) is False
    assert internal.get_by_id(draft_id) == foreign
    assert internal.get_history(draft_id) == history


def test_http_organization_dependency_has_no_implicit_tenant_fallback():
    request = Request({"type": "http", "state": {"organization_id": "spoofed"}})
    with pytest.raises(HTTPException) as error:
        authenticated_organization_id(request)
    assert error.value.status_code == 401


@pytest.mark.parametrize("path", [f"{CONFIG}/current", f"{CONFIG}/versions", f"{DRAFTS}/current", f"{DRAFTS}/unknown/history"])
def test_configuration_and_drafts_require_a_session(path):
    with TestClient(app, headers={"X-Auth-Enforce": "1"}) as anonymous:
        assert anonymous.get(path).status_code == 401

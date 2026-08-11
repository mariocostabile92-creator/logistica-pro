import json
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_credentials_service as service
from app.plugins.workforce.domain.driver_shift_credentials import (
    DriverShiftCredentialNotFoundError,
)
from app.workspace.reset_service import reset_workspace
from tests.test_driver_shift_distribution import BASE, ORG, _member, _planning, _scenario, _shift


def _distribution(client: TestClient, planning_id: int) -> dict:
    response = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution")
    assert response.status_code == 200
    return response.json()


def _prepare(client: TestClient, distribution_id: int):
    return client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/credentials/prepare"
    )


def test_prepare_one_recipient_is_one_time_hashed_and_idempotent():
    planning_id, members = _scenario(1)
    client = TestClient(app)
    distribution_id = _distribution(client, planning_id)["distribution"]["id"]

    first = _prepare(client, distribution_id)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store, private, max-age=0"
    credential = first.json()["initial_credentials"][0]
    assert first.json()["summary"] == {
        "recipients_total": 1,
        "credentials_ready": 1,
        "already_existing": 0,
        "newly_created": 1,
        "revoked": 0,
        "reset_required": 0,
        "missing": 0,
        "errors": 0,
    }
    assert len(credential["access_code"]) == 8
    assert credential["initial_pin"].isdigit() and len(credential["initial_pin"]) == 6
    assert service.verify_credential(ORG, credential["access_code"], credential["initial_pin"])

    second = _prepare(client, distribution_id)
    assert second.status_code == 200
    assert second.json()["initial_credentials"] == []
    assert second.json()["summary"]["newly_created"] == 0
    assert second.json()["summary"]["already_existing"] == 1
    fetched = client.get(f"{BASE}/driver-shift-distributions/{distribution_id}/credentials")
    assert "initial_pin" not in fetched.text and "access_code" not in fetched.text

    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM driver_shift_driver_credentials WHERE workforce_member_id=?",
            (members[0],),
        ).fetchone()
        assert row["pin_hash"].startswith("pbkdf2_sha256$")
        assert credential["initial_pin"] not in row["pin_hash"]
        assert credential["access_code"] not in row["access_code_hash"]


def test_prepare_200_recipients_is_distinct_batched_and_scoped():
    planning_id, members = _scenario(200)
    outsider = _member("OUTSIDE-200", "Outside Recipient")
    client = TestClient(app)
    distribution_id = _distribution(client, planning_id)["distribution"]["id"]

    started = perf_counter()
    response = _prepare(client, distribution_id)
    elapsed = perf_counter() - started
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["recipients_total"] == 200
    assert body["summary"]["credentials_ready"] == 200
    assert body["summary"]["newly_created"] == 200
    assert len(body["initial_credentials"]) == 200
    assert len({item["access_code"] for item in body["initial_credentials"]}) == 200
    assert len({item["initial_pin"] for item in body["initial_credentials"]}) == 200
    assert elapsed < 90
    with db_session() as conn:
        rows = conn.execute(
            "SELECT workforce_member_id, pin_hash FROM driver_shift_driver_credentials"
        ).fetchall()
        assert len(rows) == 200
        assert outsider not in {int(row["workforce_member_id"]) for row in rows}
        assert len({row["pin_hash"] for row in rows}) == 200
    assert set(members).issubset({recipient["workforce_member_id"] for recipient in body["recipients"]})


def test_credential_is_reused_by_later_distribution():
    first_planning, members = _scenario(1)
    client = TestClient(app)
    first_id = _distribution(client, first_planning)["distribution"]["id"]
    initial = _prepare(client, first_id).json()["initial_credentials"][0]

    with db_session() as conn:
        conn.execute("UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?", (first_planning,))
    second_planning = _planning(
        version=2,
        label="Settimana successiva",
        period_start="2026-08-24",
        period_end="2026-08-30",
    )
    _shift(second_planning, members[0], "2026-08-24", version=2)
    second_id = _distribution(client, second_planning)["distribution"]["id"]
    second = _prepare(client, second_id).json()

    assert second["summary"]["already_existing"] == 1
    assert second["summary"]["newly_created"] == 0
    assert second["initial_credentials"] == []
    assert service.verify_credential(ORG, initial["access_code"], initial["initial_pin"])


def test_reset_invalidates_old_pin_and_revoke_denies_verification():
    planning_id, members = _scenario(1)
    client = TestClient(app)
    distribution_id = _distribution(client, planning_id)["distribution"]["id"]
    initial = _prepare(client, distribution_id).json()["initial_credentials"][0]

    reset = client.post(f"{BASE}/credentials/{members[0]}/reset")
    assert reset.status_code == 200
    assert reset.headers["cache-control"] == "no-store, private, max-age=0"
    assert reset.json()["generation"] == 2
    assert reset.json()["initial_pin"] != initial["initial_pin"]
    assert not service.verify_credential(ORG, initial["access_code"], initial["initial_pin"])
    assert service.verify_credential(ORG, initial["access_code"], reset.json()["initial_pin"])

    revoked = client.post(f"{BASE}/credentials/{members[0]}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["credential_status"] == "REVOKED"
    assert not service.verify_credential(ORG, initial["access_code"], reset.json()["initial_pin"])


def test_cross_organization_reset_revoke_and_read_are_blocked():
    other_org = "credential-other-org"
    member = _member("CROSS-1", "Cross Tenant", other_org)
    planning = _planning(organization_id=other_org)
    _shift(planning, member, "2026-08-17", organization_id=other_org)
    with pytest.raises(DriverShiftCredentialNotFoundError):
        service.reset_credential(ORG, member, "admin@test")
    with pytest.raises(DriverShiftCredentialNotFoundError):
        service.revoke_credential(ORG, member, "admin@test")


def test_audit_never_contains_pin_or_access_code():
    planning_id, members = _scenario(1)
    client = TestClient(app)
    distribution_id = _distribution(client, planning_id)["distribution"]["id"]
    credential = _prepare(client, distribution_id).json()["initial_credentials"][0]
    reset_pin = client.post(f"{BASE}/credentials/{members[0]}/reset").json()["initial_pin"]
    client.post(f"{BASE}/credentials/{members[0]}/revoke")

    with db_session() as conn:
        rows = conn.execute(
            "SELECT actor, reason, after_value FROM workforce_changes WHERE entity_type='driver_shift_driver_credential'"
        ).fetchall()
    assert [row["reason"] for row in rows] == [
        "driver_shift_credentials_created",
        "driver_shift_credentials_reset",
        "driver_shift_credentials_revoked",
    ]
    serialized = json.dumps([dict((key, row[key]) for key in row.keys()) for row in rows])
    assert credential["initial_pin"] not in serialized
    assert reset_pin not in serialized
    assert credential["access_code"] not in serialized


def test_workspace_reset_removes_credentials_before_workforce_parent():
    planning_id, _ = _scenario(1)
    client = TestClient(app)
    distribution_id = _distribution(client, planning_id)["distribution"]["id"]
    _prepare(client, distribution_id)
    token = bind_organization(ORG)
    try:
        result = reset_workspace(actor="admin@test")
    finally:
        reset_organization(token)
    assert result.removed_counts.driver_shift_driver_credentials == 1
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM driver_shift_driver_credentials").fetchone()["total"] == 0

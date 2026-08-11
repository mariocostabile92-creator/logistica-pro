from time import perf_counter

from fastapi.testclient import TestClient

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_distribution_service as service
from app.plugins.workforce.domain.driver_shift_distribution import DriverShiftDistributionError
from app.workspace.reset_service import reset_workspace


ORG = "test-organization"
BASE = "/api/plugins/workforce/v1"


def _member(external_id: str, name: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO workforce_members (
                   external_identifier, display_name, capabilities, active,
                   source_reference, created_at, updated_at, organization_id
               ) VALUES (?, ?, '[]', 1, 'delivery-test',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', ?)""",
            (external_id, name, organization_id),
        )
        return int(cursor.lastrowid)


def _planning(status: str = "ACTIVE", *, version: int = 1,
              organization_id: str = ORG, label: str = "Settimana QA") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO driver_shift_plannings (
                   organization_id, label, period_start, period_end, status,
                   version, created_at, created_by, updated_at, published_at, published_by
               ) VALUES (?, ?, '2026-08-17', '2026-08-23', ?, ?,
                         '2026-08-11T09:00:00Z', 'qa@test',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', 'qa@test')""",
            (organization_id, label, status, version),
        )
        return int(cursor.lastrowid)


def _shift(planning_id: int, member_id: int, operation_date: str, *,
           shift: str = "A", available: int = 1, organization_id: str = ORG,
           version: int = 1) -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO driver_shift_planning_published_rows (
                   organization_id, driver_shift_planning_id, planning_version,
                   workforce_member_id, operational_date, status_code, availability,
                   shift_code, start_time, end_time, station, transporter_id,
                   provenance_summary, published_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DLO2', ?, '[]',
                         '2026-08-11T09:00:00Z')""",
            (organization_id, planning_id, version, member_id, operation_date,
             "scheduled" if available else "rest", available, shift if available else None,
             "08:00" if available else None, "17:00" if available else None,
             f"T-{member_id}"),
        )


def _scenario(driver_count: int = 3) -> tuple[int, list[int]]:
    planning_id = _planning()
    members = []
    for index in range(driver_count):
        member_id = _member(f"WF-{index + 1}", ["Mario Rossi", "Yassine Zyadi", "Anna Verdi"][index] if index < 3 else f"Driver {index}")
        members.append(member_id)
        _shift(planning_id, member_id, "2026-08-17")
        _shift(planning_id, member_id, "2026-08-18", shift="R", available=0)
    return planning_id, members


def _token(client: TestClient, distribution: dict, recipient_index: int = 0) -> str:
    recipient = distribution["recipients"][recipient_index]
    response = client.post(
        f"{BASE}/driver-shift-distributions/{distribution['distribution']['id']}/recipients/{recipient['id']}/access-link"
    )
    assert response.status_code == 200
    return response.json()["access_url"].split("#token=", 1)[1]


def test_prepare_requires_active_and_is_idempotent_with_distinct_recipients():
    draft = _planning("DRAFT")
    client = TestClient(app)
    assert client.post(f"{BASE}/driver-shift-plannings/{draft}/distribution").status_code == 422
    planning_id, _ = _scenario()
    first = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution")
    second = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution")
    assert first.status_code == second.status_code == 200
    assert first.json()["distribution"]["id"] == second.json()["distribution"]["id"]
    assert first.json()["summary"] == {
        "recipients_total": 3, "ready": 3, "pending": 0,
        "contact_ready": 0, "missing_contact": 3,
        "invalid_contact": 0, "excluded": 0,
        "opened": 0, "acknowledged": 0, "not_opened": 3,
    }
    assert [item["shift_days_count"] for item in first.json()["recipients"]] == [2, 2, 2]
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM driver_shift_distribution_recipients").fetchone()["total"] == 3


def test_personal_token_returns_only_its_driver_in_chronological_order_without_sensitive_fields():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    token = _token(client, distribution)
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    response = public.get(f"/api/public/driver-shifts/{token}")
    assert response.status_code == 200
    body = response.json()
    expected_member = next(item for item in distribution["recipients"] if item["id"] == distribution["recipients"][0]["id"])
    assert body["driver_name"] == expected_member["display_name"]
    assert [item["operational_date"] for item in body["shifts"]] == ["2026-08-17", "2026-08-18"]
    assert body["shifts"][1]["availability"] is False
    serialized = str(body)
    for forbidden in ("workforce_member_id", "transporter_id", "provenance", "organization_id", "contract"):
        assert forbidden not in serialized
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_tokens_are_isolated_random_and_not_enumerable():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    token_a = _token(client, distribution, 0)
    token_b = _token(client, distribution, 1)
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    assert token_a != token_b and len(token_a) > 80
    assert public.get("/api/public/driver-shifts/random-invalid-token").status_code == 404
    assert public.get(f"/api/public/driver-shifts/{token_a}").json()["driver_name"] != public.get(
        f"/api/public/driver-shifts/{token_b}"
    ).json()["driver_name"]
    with db_session() as conn:
        row = conn.execute("SELECT access_token_hash FROM driver_shift_distribution_recipients LIMIT 1").fetchone()
        assert token_a not in row["access_token_hash"]


def test_organization_isolation_applies_to_admin_and_public_access():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    token = _token(client, distribution)
    other_member = _member("OTHER-1", "Other Driver", "other-organization")
    other_planning = _planning(organization_id="other-organization")
    _shift(other_planning, other_member, "2026-08-17", organization_id="other-organization")
    assert client.post(f"{BASE}/driver-shift-plannings/{other_planning}/distribution").status_code == 404
    assert TestClient(app, headers={"X-Test-Auth-Harness": ""}).get(
        f"/api/public/driver-shifts/{token}"
    ).json()["driver_name"] != "Other Driver"


def test_revoke_and_regenerate_invalidate_previous_token():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    recipient = distribution["recipients"][0]
    distribution_id = distribution["distribution"]["id"]
    old_token = _token(client, distribution)
    revoked = client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/recipients/{recipient['id']}/revoke"
    )
    assert revoked.status_code == 200
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    assert public.get(f"/api/public/driver-shifts/{old_token}").status_code == 404
    regenerated = client.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/recipients/{recipient['id']}/regenerate"
    )
    new_token = regenerated.json()["access_url"].split("#token=", 1)[1]
    assert regenerated.status_code == 200 and new_token != old_token
    assert public.get(f"/api/public/driver-shifts/{old_token}").status_code == 404
    assert public.get(f"/api/public/driver-shifts/{new_token}").status_code == 200


def test_expired_token_is_a_safe_not_found():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    token = _token(client, distribution)
    with db_session() as conn:
        conn.execute("UPDATE driver_shift_distribution_recipients SET access_expires_at='2020-01-01T00:00:00Z'")
    response = TestClient(app, headers={"X-Test-Auth-Harness": ""}).get(
        f"/api/public/driver-shifts/{token}"
    )
    assert response.status_code == 404
    assert "expired" not in response.text.casefold()


def test_open_tracking_and_acknowledgement_are_idempotent_and_refresh_summary():
    planning_id, _ = _scenario()
    client = TestClient(app)
    distribution = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    token = _token(client, distribution)
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    first = public.get(f"/api/public/driver-shifts/{token}").json()
    second = public.get(f"/api/public/driver-shifts/{token}").json()
    assert first["first_opened_at"] == second["first_opened_at"]
    ack_one = public.post(f"/api/public/driver-shifts/{token}/acknowledge").json()
    ack_two = public.post(f"/api/public/driver-shifts/{token}/acknowledge").json()
    assert ack_one["acknowledged_at"] == ack_two["acknowledged_at"]
    assert ack_two["access_status"] == "ACKNOWLEDGED"
    refreshed = client.get(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    assert refreshed["summary"]["opened"] == 1
    assert refreshed["summary"]["acknowledged"] == 1
    assert refreshed["summary"]["not_opened"] == 2


def test_new_active_revision_supersedes_distribution_and_revokes_old_access():
    first_planning, members = _scenario(1)
    client = TestClient(app)
    first_distribution = client.post(f"{BASE}/driver-shift-plannings/{first_planning}/distribution").json()
    old_token = _token(client, first_distribution)
    with db_session() as conn:
        conn.execute("UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?", (first_planning,))
    second_planning = _planning(version=2, label="Revisione 2")
    _shift(second_planning, members[0], "2026-08-19", version=2)
    second_distribution = client.post(f"{BASE}/driver-shift-plannings/{second_planning}/distribution")
    assert second_distribution.status_code == 200
    with db_session() as conn:
        previous = conn.execute("SELECT status FROM driver_shift_distributions WHERE id=?", (
            first_distribution["distribution"]["id"],
        )).fetchone()
        assert previous["status"] == "SUPERSEDED"
    assert TestClient(app, headers={"X-Test-Auth-Harness": ""}).get(
        f"/api/public/driver-shifts/{old_token}"
    ).status_code == 404


def test_prepare_300_recipients_uses_batch_generation():
    planning_id = _planning()
    with db_session() as conn:
        member_rows = [(f"PERF-{index}", f"Driver {index}", ORG) for index in range(300)]
        conn.executemany(
            """INSERT INTO workforce_members (
                   external_identifier, display_name, capabilities, active,
                   source_reference, created_at, updated_at, organization_id
               ) VALUES (?, ?, '[]', 1, 'delivery-performance',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', ?)""",
            member_rows,
        )
        members = conn.execute(
            "SELECT id FROM workforce_members WHERE organization_id=? ORDER BY id", (ORG,),
        ).fetchall()
        conn.executemany(
            """INSERT INTO driver_shift_planning_published_rows (
                   organization_id, driver_shift_planning_id, planning_version,
                   workforce_member_id, operational_date, status_code, availability,
                   shift_code, station, provenance_summary, published_at
               ) VALUES (?, ?, 1, ?, '2026-08-17', 'scheduled', 1, 'A', 'DLO2', '[]',
                         '2026-08-11T09:00:00Z')""",
            [(ORG, planning_id, row["id"]) for row in members],
        )
    started = perf_counter()
    model = service.prepare_distribution(ORG, planning_id, "performance@test")
    elapsed = perf_counter() - started
    assert model.summary.recipients_total == 300
    assert elapsed < 5


def test_workspace_reset_includes_distribution_tables():
    planning_id, _ = _scenario(1)
    service.prepare_distribution(ORG, planning_id, "qa@test")
    tenant = bind_organization(ORG)
    try:
        result = reset_workspace(actor="qa@test")
    finally:
        reset_organization(tenant)
    assert result.removed_counts.driver_shift_distributions == 1
    assert result.removed_counts.driver_shift_distribution_recipients == 1
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM driver_shift_distributions").fetchone()["total"] == 0

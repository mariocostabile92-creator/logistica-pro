import json
from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.damage.interfaces import router as damage_router


client = TestClient(app)
POLICY = "/api/fleet/damage-cases/policy"
NOW = "2026-08-08T12:00:00+00:00"
ASSET_SEQUENCE = count(1)


def _member(organization_id: str = "test-organization") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, 'Mario Rossi', 'driver', '[]', 1,
                      'damage-policy-api-test', ?, ?)
            """,
            (organization_id, f"DRV-{organization_id}", NOW, NOW),
        )
        return int(cursor.lastrowid)


def _case(member_id: int, occurred_at: str, status: str = "nuova") -> None:
    sequence = next(ASSET_SEQUENCE)
    with db_session() as conn:
        asset = conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category, status,
                availability, capabilities, created_at, updated_at
            ) VALUES ('test-organization', ?, ?, 'van', 'active',
                      'available', '[]', ?, ?)
            """,
            (f"POL-{sequence}", f"P{sequence:05d}AA", NOW, NOW),
        )
        asset_id = int(asset.lastrowid)
        conn.execute(
            """
            INSERT INTO damage_cases (
                case_number, vehicle_id, occurred_at, created_at, updated_at,
                origin, description, severity, status,
                vehicle_operational_status, driver_workforce_member_id
            ) VALUES (?, ?, ?, ?, ?, 'manual', 'Policy API test', 'media', ?,
                      'disponibile', ?)
            """,
            (f"DMG-{asset_id}", asset_id, occurred_at, NOW, NOW, status, member_id),
        )


def _save_payload(**changes):
    payload = {
        "enabled": True,
        "free_events_count": 1,
        "counting_period": "all_time",
    }
    payload.update(changes)
    return payload


def test_get_returns_safe_default_policy_for_authenticated_organization():
    response = client.get(POLICY)

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "free_events_count": 0,
        "counting_period": "all_time",
        "updated_at": None,
    }


def test_put_persists_and_get_returns_current_policy():
    saved = client.put(POLICY, json=_save_payload(
        free_events_count=2,
        counting_period="calendar_year",
    ))
    current = client.get(POLICY)

    assert saved.status_code == 200
    assert current.json()["enabled"] is True
    assert current.json()["free_events_count"] == 2
    assert current.json()["counting_period"] == "calendar_year"
    assert current.json()["updated_at"]


@pytest.mark.parametrize(
    "payload",
    [
        _save_payload(free_events_count=-1),
        _save_payload(counting_period="monthly"),
        {**_save_payload(), "organization_id": "other-organization"},
    ],
)
def test_put_rejects_invalid_or_client_scoped_configuration(payload):
    assert client.put(POLICY, json=payload).status_code == 422


def test_put_requires_existing_configuration_permission(monkeypatch):
    monkeypatch.setattr(damage_router, "has_permission", lambda _role, _permission: False)

    response = client.put(POLICY, json=_save_payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "Permesso di configurazione richiesto."


def test_policy_is_organization_scoped_and_client_cannot_override_scope():
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO damage_policies (
                organization_id, enabled, free_events_count, counting_period,
                created_at, updated_at
            ) VALUES ('other-organization', 1, 9, 'rolling_12_months', ?, ?)
            """,
            (NOW, NOW),
        )

    current = client.get(POLICY).json()
    client.put(POLICY, json=_save_payload(free_events_count=3))

    with db_session() as conn:
        foreign = conn.execute(
            "SELECT * FROM damage_policies WHERE organization_id='other-organization'"
        ).fetchone()
    assert current["free_events_count"] == 0
    assert current["counting_period"] == "all_time"
    assert foreign["free_events_count"] == 9
    assert foreign["counting_period"] == "rolling_12_months"


def test_policy_change_writes_explicit_server_actor_audit_with_old_and_new():
    response = client.put(POLICY, json=_save_payload(free_events_count=4))

    assert response.status_code == 200
    with db_session() as conn:
        event = conn.execute(
            "SELECT * FROM admin_audit_events WHERE action='damage_policy_changed'"
        ).fetchone()
    target = json.loads(event["target"])
    assert event["organization_id"] == "test-organization"
    assert event["user_id"] == "test-harness-administrator"
    assert event["created_at"]
    assert target["old"]["enabled"] is False
    assert target["new"]["free_events_count"] == 4


def test_driver_policy_state_returns_complete_disabled_state():
    member_id = _member()
    _case(member_id, "2026-08-01T09:00:00Z")

    response = client.get(
        f"/api/fleet/damage-cases/drivers/{member_id}/policy-state",
        params={"reference_date": "2026-08-08"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "policy_enabled": False,
        "total_attributed_cases": 1,
        "countable_cases": 1,
        "free_events_count": 0,
        "free_events_used": 0,
        "events_over_threshold": 0,
        "next_event_is_over_threshold": False,
        "counting_period": "all_time",
        "period_start": None,
        "period_end": None,
    }


@pytest.mark.parametrize(
    ("period", "expected_count", "start", "end"),
    [
        ("all_time", 3, None, None),
        ("calendar_year", 1, "2026-01-01", "2026-12-31"),
        ("rolling_12_months", 2, "2025-08-08", "2026-08-08"),
    ],
)
def test_driver_policy_state_supports_all_counting_periods(
    period, expected_count, start, end
):
    member_id = _member()
    _case(member_id, "2025-01-01T09:00:00Z")
    _case(member_id, "2025-08-08T09:00:00Z")
    _case(member_id, "2026-01-01T09:00:00Z")
    client.put(POLICY, json=_save_payload(counting_period=period))

    state = client.get(
        f"/api/fleet/damage-cases/drivers/{member_id}/policy-state",
        params={"reference_date": "2026-08-08"},
    ).json()

    assert state["countable_cases"] == expected_count
    assert state["period_start"] == start
    assert state["period_end"] == end


def test_driver_policy_state_applies_free_event_threshold_without_persisting_counts():
    member_id = _member()
    _case(member_id, "2026-07-01T09:00:00Z")
    _case(member_id, "2026-08-01T09:00:00Z")
    client.put(POLICY, json=_save_payload(free_events_count=1))

    state = client.get(
        f"/api/fleet/damage-cases/drivers/{member_id}/policy-state"
    ).json()

    assert state["free_events_used"] == 1
    assert state["events_over_threshold"] == 1
    assert state["next_event_is_over_threshold"] is True


def test_driver_policy_state_rejects_foreign_driver():
    foreign_member = _member("other-organization")

    response = client.get(
        f"/api/fleet/damage-cases/drivers/{foreign_member}/policy-state"
    )

    assert response.status_code == 404


def test_policy_endpoints_are_declared_before_dynamic_damage_case_route():
    paths = [route.path for route in damage_router.router.routes]

    assert paths.index("/api/fleet/damage-cases/policy") < paths.index(
        "/api/fleet/damage-cases/{case_id}"
    )
    assert paths.index(
        "/api/fleet/damage-cases/drivers/{workforce_member_id}/policy-state"
    ) < paths.index("/api/fleet/damage-cases/{case_id}")

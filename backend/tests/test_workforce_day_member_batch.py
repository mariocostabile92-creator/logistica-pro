from fastapi.testclient import TestClient
import pytest

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import day_member_batch_service
from app.plugins.workforce.domain.errors import WorkforceMemberNotFoundError
from app.plugins.workforce.infrastructure import day_member_batch_repository


BASE = "/api/plugins/workforce/v1"
ORG = "test-organization"
client = TestClient(app)


def _member(identifier: str, cycle: str = "NEXT_DAY", organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, operational_cycle,
                capabilities, active, source_reference, created_at,
                updated_at, organization_id
            ) VALUES (?, ?, ?, '[]', 1, 'day-member-test', ?, ?, ?)
            """,
            (
                identifier,
                identifier,
                cycle,
                "2026-08-13T08:00:00Z",
                "2026-08-13T08:00:00Z",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _existing(member_id: int, status: str = "scheduled", shift: str | None = "SA"):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                shift_code, operational_activity, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, '2026-08-17', ?, ?, ?, 'Legacy', 'import',
                      'imported', '2026-08-13T08:00:00Z', ?)
            """,
            (member_id, status, int(status in {"scheduled", "available"}), shift, ORG),
        )


def _payload(member_ids: list[int], **overrides):
    return {
        "operational_date": "2026-08-17",
        "workforce_member_ids": member_ids,
        "status_code": "scheduled",
        "shift_code": "C1",
        "operational_activity": "Consegna DLO2",
        **overrides,
    }


def _rows():
    with db_session() as conn:
        return [dict(row) for row in conn.execute(
            """
            SELECT workforce_member_id, date, status_code, shift_code,
                   operational_activity, organization_id
            FROM workforce_day_statuses ORDER BY workforce_member_id
            """
        ).fetchall()]


def test_batch_members_applies_one_day_to_multiple_members_and_persists_activity():
    members = [_member(f"Driver {index}") for index in range(3)]

    response = client.post(f"{BASE}/day-status/batch-members", json=_payload(members))

    assert response.status_code == 200, response.text
    assert response.json()["applied_count"] == 3
    assert {row["shift_code"] for row in _rows()} == {"C1"}
    assert {row["operational_activity"] for row in _rows()} == {"Consegna DLO2"}


def test_batch_members_is_atomic_and_rolls_back(monkeypatch):
    members = [_member("Atomic A"), _member("Atomic B")]
    original = day_member_batch_repository._save_batch_status
    calls = 0

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated atomic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(day_member_batch_repository, "_save_batch_status", fail_on_second)
    with pytest.raises(RuntimeError, match="simulated atomic failure"):
        day_member_batch_service.apply(_payload(members), "dispatcher", ORG)
    assert _rows() == []


def test_batch_members_is_strictly_organization_scoped():
    foreign = _member("Foreign", organization_id="other-organization")
    with pytest.raises(WorkforceMemberNotFoundError):
        day_member_batch_service.apply(_payload([foreign]), "dispatcher", ORG)
    assert _rows() == []


def test_empty_only_is_default_and_skips_existing_rows():
    existing = _member("Existing")
    empty = _member("Empty")
    _existing(existing)

    response = client.post(
        f"{BASE}/day-status/batch-members",
        json=_payload([existing, empty]),
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["applied_count"], body["skipped_count"]) == (1, 1)
    assert body["warnings"][0]["code"] == "EXISTING_STATUS_SKIPPED"
    assert {row["workforce_member_id"]: row["shift_code"] for row in _rows()} == {
        existing: "SA", empty: "C1"
    }


def test_replace_selected_requires_explicit_overwrite_confirmation():
    member = _member("Overwrite")
    _existing(member)
    response = client.post(
        f"{BASE}/day-status/batch-members",
        json=_payload([member], overwrite_policy="REPLACE_SELECTED"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["existing_count"] == 1
    assert _rows()[0]["shift_code"] == "SA"


def test_replace_selected_overwrites_only_after_confirmation():
    member = _member("Confirmed")
    _existing(member)
    response = client.post(
        f"{BASE}/day-status/batch-members",
        json=_payload(
            [member],
            overwrite_policy="REPLACE_SELECTED",
            confirm_overwrite=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["overwritten_count"] == 1
    assert _rows()[0]["shift_code"] == "C1"


@pytest.mark.parametrize("protected_status", ["rest", "holiday", "sickness", "leave", "unavailable"])
def test_absence_or_unavailable_requires_specific_override_confirmation(protected_status: str):
    member = _member(f"Protected {protected_status}")
    _existing(member, protected_status, None)
    response = client.post(
        f"{BASE}/day-status/batch-members",
        json=_payload(
            [member],
            overwrite_policy="REPLACE_SELECTED",
            confirm_overwrite=True,
        ),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["protected_count"] == 1

    confirmed = client.post(
        f"{BASE}/day-status/batch-members",
        json=_payload(
            [member],
            overwrite_policy="REPLACE_SELECTED",
            confirm_overwrite=True,
            confirm_unavailable_override=True,
        ),
    )
    assert confirmed.status_code == 200, confirmed.text


def test_member_cycle_is_preserved_and_changes_are_audited():
    member = _member("Same Day", cycle="SAME_DAY")
    response = client.post(f"{BASE}/day-status/batch-members", json=_payload([member]))
    assert response.status_code == 200
    with db_session() as conn:
        cycle = conn.execute(
            "SELECT operational_cycle FROM workforce_members WHERE id = ?", (member,)
        ).fetchone()["operational_cycle"]
        change = conn.execute(
            "SELECT reason, source FROM workforce_changes ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert cycle == "SAME_DAY"
    assert dict(change) == {
        "reason": "manual_day_member_batch_update",
        "source": "manual_day_planning",
    }

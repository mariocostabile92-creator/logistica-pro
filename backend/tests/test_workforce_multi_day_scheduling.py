from fastapi.testclient import TestClient
import pytest

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import workforce_service
from app.plugins.workforce.domain.errors import WorkforceMemberNotFoundError
from app.plugins.workforce.infrastructure import write_repository


BASE = "/api/plugins/workforce/v1"
client = TestClient(app)


def _member(identifier: str, name: str, organization_id: str = "default") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'multi-day-test', ?, ?, ?)
            """,
            (
                identifier,
                name,
                "2026-08-12T08:00:00Z",
                "2026-08-12T08:00:00Z",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _batch(member_id: int, dates: list[str], organization_id: str = "default", **overrides):
    values = {
        "workforce_member_id": member_id,
        "dates": dates,
        "status_code": "scheduled",
        "shift_code": "C1",
        "source_reference": "manual_bulk",
        **overrides,
    }
    return workforce_service.save_day_statuses_batch(
        values,
        "dispatcher@test",
        organization_id,
    )


def _rows(member_id: int) -> list[dict]:
    with db_session() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, status_code, shift_code, organization_id
                FROM workforce_day_statuses
                WHERE workforce_member_id = ?
                ORDER BY date
                """,
                (member_id,),
            ).fetchall()
        ]


def test_batch_endpoint_updates_one_selected_day():
    member_id = _member("WF-ONE", "Alban Beqiraj", "test-organization")

    response = client.post(
        f"{BASE}/day-status/batch",
        json={
            "workforce_member_id": member_id,
            "dates": ["2026-08-10"],
            "status_code": "scheduled",
            "shift_code": "C1",
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    assert _rows(member_id)[0]["shift_code"] == "C1"


@pytest.mark.parametrize("day_count", [5, 7])
def test_batch_updates_five_or_seven_days_for_one_driver(day_count: int):
    member_id = _member(f"WF-{day_count}", f"Driver {day_count}")
    dates = [f"2026-08-{day:02d}" for day in range(10, 10 + day_count)]

    result = _batch(member_id, dates)

    assert len(result) == day_count
    assert [row["date"] for row in _rows(member_id)] == dates
    assert {row["shift_code"] for row in _rows(member_id)} == {"C1"}


def test_batch_is_atomic_and_rolls_back_every_day(monkeypatch):
    member_id = _member("WF-ROLLBACK", "Rollback Driver")
    original = write_repository._save_batch_status
    calls = 0

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated batch failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(write_repository, "_save_batch_status", fail_on_second)

    with pytest.raises(RuntimeError, match="simulated batch failure"):
        _batch(member_id, ["2026-08-10", "2026-08-11", "2026-08-12"])

    assert _rows(member_id) == []


def test_batch_is_strictly_organization_scoped():
    member_id = _member("WF-SHARED", "Organization B", "organization-b")

    with pytest.raises(WorkforceMemberNotFoundError):
        _batch(member_id, ["2026-08-10"], "organization-a")

    assert _rows(member_id) == []


def test_batch_changes_only_selected_driver_and_selected_dates():
    alban_id = _member("WF-ALBAN", "Alban Beqiraj")
    other_id = _member("WF-OTHER", "Other Driver")
    full_week = [f"2026-08-{day:02d}" for day in range(10, 17)]
    weekdays = full_week[:5]
    weekend = full_week[5:]
    _batch(alban_id, full_week, status_code="rest", shift_code=None)
    _batch(other_id, full_week, status_code="rest", shift_code=None)

    _batch(alban_id, weekdays)

    alban = _rows(alban_id)
    assert [row["shift_code"] for row in alban[:5]] == ["C1"] * 5
    assert [(row["status_code"], row["shift_code"]) for row in alban[5:]] == [
        ("rest", None),
        ("rest", None),
    ]
    assert {row["status_code"] for row in _rows(other_id)} == {"rest"}
    assert [row["date"] for row in alban if row["status_code"] == "scheduled"] == weekdays
    assert [row["date"] for row in alban if row["status_code"] == "rest"] == weekend

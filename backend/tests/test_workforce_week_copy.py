from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import week_copy_service
from app.plugins.workforce.domain.errors import WorkforceMemberNotFoundError
from app.plugins.workforce.domain.week_copy import WorkforceWeekCopyConflictError
from app.plugins.workforce.infrastructure import write_repository


BASE = "/api/plugins/workforce/v1"
client = TestClient(app)


def _member(identifier: str, organization_id: str = "default") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'week-copy-test', ?, ?, ?)
            """,
            (
                identifier,
                identifier,
                "2026-08-12T08:00:00Z",
                "2026-08-12T08:00:00Z",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _status(
    member_id: int,
    day: str,
    *,
    status_code: str = "scheduled",
    shift_code: str | None = "C1",
    notes: str | None = None,
    organization_id: str = "default",
):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                shift_code, start_time, end_time, notes, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, ?, '08:30', '17:30', ?, 'seed',
                      'manual', ?, ?)
            """,
            (
                member_id,
                day,
                status_code,
                int(status_code == "scheduled"),
                shift_code,
                notes,
                f"{day}T08:00:00Z",
                organization_id,
            ),
        )


def _week(member_id: int, monday: str, organization_id: str = "default"):
    start = date.fromisoformat(monday)
    for offset in range(7):
        weekend = offset >= 5
        _status(
            member_id,
            (start + timedelta(days=offset)).isoformat(),
            status_code="rest" if weekend else "scheduled",
            shift_code=None if weekend else "C1",
            notes="weekend" if weekend else "weekday",
            organization_id=organization_id,
        )


def _rows(member_id: int):
    with db_session() as conn:
        return [dict(row) for row in conn.execute(
            """
            SELECT date, status_code, availability, shift_code, start_time,
                   end_time, notes, source_reference, organization_id
            FROM workforce_day_statuses
            WHERE workforce_member_id = ?
            ORDER BY date
            """,
            (member_id,),
        ).fetchall()]


def test_preview_maps_same_driver_exactly_minus_seven_days():
    member_id = _member("WF-WEEK-PREVIEW")
    _week(member_id, "2026-08-10")

    preview = week_copy_service.preview(member_id, "2026-08-17", "default")

    assert preview.workforce_member_id == member_id
    assert (preview.source_week_start, preview.source_week_end) == (
        "2026-08-10", "2026-08-16"
    )
    assert (preview.target_week_start, preview.target_week_end) == (
        "2026-08-17", "2026-08-23"
    )
    assert len(preview.days) == 7
    assert [(item.source_date, item.target_date) for item in preview.days] == [
        (f"2026-08-{day:02d}", f"2026-08-{day + 7:02d}")
        for day in range(10, 17)
    ]
    assert [item.source.shift_code for item in preview.days[:5]] == ["C1"] * 5
    assert [item.source.status_code for item in preview.days[5:]] == ["rest", "rest"]


def test_partial_source_keeps_missing_target_days_unchanged():
    member_id = _member("WF-WEEK-PARTIAL")
    for day in (10, 11, 13, 14, 16):
        _status(member_id, f"2026-08-{day:02d}")
    _status(member_id, "2026-08-19", status_code="leave", shift_code=None)
    _status(member_id, "2026-08-22", status_code="sickness", shift_code=None)

    preview = week_copy_service.preview(member_id, "2026-08-17", "default")
    result = week_copy_service.apply(
        member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
    )

    assert preview.missing_count == 2
    assert result.copied_count == 5
    target = {row["date"]: row for row in _rows(member_id) if row["date"] >= "2026-08-17"}
    assert target["2026-08-19"]["status_code"] == "leave"
    assert target["2026-08-22"]["status_code"] == "sickness"
    assert target["2026-08-17"]["shift_code"] == "C1"


def test_existing_target_is_detected_and_overwritten_only_after_confirmation():
    member_id = _member("WF-WEEK-OVERWRITE")
    _week(member_id, "2026-08-10")
    _status(member_id, "2026-08-17", shift_code="SA")

    preview = week_copy_service.preview(member_id, "2026-08-17", "default")
    assert preview.overwrite_count == 1
    assert preview.days[0].target.shift_code == "SA"
    assert _rows(member_id)[-1]["shift_code"] == "SA"

    week_copy_service.apply(
        member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
    )
    assert {row["date"]: row for row in _rows(member_id)}["2026-08-17"]["shift_code"] == "C1"


def test_apply_copies_all_supported_fields_and_leaves_source_unchanged():
    member_id = _member("WF-WEEK-FIELDS")
    _week(member_id, "2026-08-10")
    source_before = [row.copy() for row in _rows(member_id)]
    preview = week_copy_service.preview(member_id, "2026-08-17", "default")

    result = week_copy_service.apply(
        member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
    )

    rows = _rows(member_id)
    assert rows[:7] == source_before
    assert result.copied_count == 7
    assert [(row["status_code"], row["availability"], row["shift_code"],
             row["start_time"], row["end_time"], row["notes"])
            for row in rows[7:]] == [
        (row["status_code"], row["availability"], row["shift_code"],
         row["start_time"], row["end_time"], row["notes"])
        for row in source_before
    ]
    assert {row["source_reference"] for row in rows[7:]} == {
        "copied_from_previous_week"
    }


def test_week_copy_is_strictly_organization_scoped():
    member_id = _member("WF-WEEK-ORG-B", "organization-b")
    _week(member_id, "2026-08-10", "organization-b")

    with pytest.raises(WorkforceMemberNotFoundError):
        week_copy_service.preview(member_id, "2026-08-17", "organization-a")

    assert len(_rows(member_id)) == 7


def test_week_copy_rolls_back_atomically(monkeypatch):
    member_id = _member("WF-WEEK-ROLLBACK")
    _week(member_id, "2026-08-10")
    preview = week_copy_service.preview(member_id, "2026-08-17", "default")
    original = write_repository._save_batch_status
    calls = 0

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated week copy failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(write_repository, "_save_batch_status", fail_on_second)
    with pytest.raises(RuntimeError, match="simulated week copy failure"):
        week_copy_service.apply(
            member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
        )

    assert len(_rows(member_id)) == 7


def test_stale_preview_rejected_without_overwrite():
    member_id = _member("WF-WEEK-STALE")
    _week(member_id, "2026-08-10")
    preview = week_copy_service.preview(member_id, "2026-08-17", "default")
    _status(member_id, "2026-08-17", shift_code="SA")

    with pytest.raises(WorkforceWeekCopyConflictError):
        week_copy_service.apply(
            member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
        )

    assert _rows(member_id)[-1]["shift_code"] == "SA"


def test_apply_writes_copy_week_audit_metadata():
    member_id = _member("WF-WEEK-AUDIT")
    _status(member_id, "2026-08-10")
    preview = week_copy_service.preview(member_id, "2026-08-17", "default")
    week_copy_service.apply(
        member_id, "2026-08-17", preview.fingerprint, "dispatcher@test", "default"
    )

    with db_session() as conn:
        change = dict(conn.execute(
            """
            SELECT reason, source, actor, organization_id, after_value
            FROM workforce_changes ORDER BY id DESC LIMIT 1
            """
        ).fetchone())
    assert change["reason"] == "copied_from_previous_week"
    assert change["source"] == "copy_week"
    assert change["actor"] == "dispatcher@test"
    assert '"date": "2026-08-17"' in change["after_value"]


@pytest.mark.parametrize(
    ("source_start", "target_start"),
    [("2026-07-27", "2026-08-03"), ("2026-12-28", "2027-01-04")],
)
def test_month_and_year_boundaries(source_start: str, target_start: str):
    member_id = _member(f"WF-WEEK-{target_start}")
    _week(member_id, source_start)
    preview = week_copy_service.preview(member_id, target_start, "default")

    assert preview.source_week_start == source_start
    assert preview.target_week_start == target_start
    assert len(preview.days) == 7


def test_preview_and_apply_endpoints_are_organization_scoped_and_return_409():
    member_id = _member("WF-WEEK-ENDPOINT", "test-organization")
    _week(member_id, "2026-08-10", "test-organization")
    preview_response = client.get(
        f"{BASE}/week-copy/preview",
        params={
            "workforce_member_id": member_id,
            "target_week_start": "2026-08-17",
        },
    )
    assert preview_response.status_code == 200, preview_response.text
    fingerprint = preview_response.json()["fingerprint"]
    _status(
        member_id,
        "2026-08-17",
        shift_code="SA",
        organization_id="test-organization",
    )

    apply_response = client.post(
        f"{BASE}/week-copy",
        json={
            "workforce_member_id": member_id,
            "target_week_start": "2026-08-17",
            "expected_fingerprint": fingerprint,
        },
    )
    assert apply_response.status_code == 409, apply_response.text
    assert apply_response.json()["detail"]["code"] == "WORKFORCE_WEEK_COPY_STALE"

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import coverage_service, manual_coverage_service
from app.plugins.workforce.domain.coverage import ImportedDailyCoverageRequirement
from app.plugins.workforce.infrastructure import (
    coverage_repository,
    manual_coverage_repository,
)
from app.utils.date_utils import utc_now_iso


BASE = "/api/plugins/workforce/v1/planning/coverage"
DAY = "2026-08-15"
ORG = "test-organization"
client = TestClient(app)


def _coverage(organization_id: str = ORG) -> dict:
    if organization_id == ORG:
        response = client.get(
            BASE, params={"date_from": DAY, "date_to": DAY}
        )
        assert response.status_code == 200, response.text
        return response.json()
    return coverage_service.daily_coverage(
        organization_id, DAY, DAY
    ).model_dump(mode="json")


def _save(requirements: list[dict], fingerprint: str | None = None):
    current = _coverage()
    return client.put(
        f"{BASE}/{DAY}",
        json={
            "expected_fingerprint": fingerprint or current["fingerprint"],
            "requirements": requirements,
        },
    )


def _imported(
    forecast: int,
    *,
    source_identity: str,
    source: str = "IMPORT",
) -> None:
    requirement = ImportedDailyCoverageRequirement(
        operational_date=DAY,
        station=None,
        operational_cycle="NEXT_DAY",
        coverage_segment=None,
        forecast_routes=forecast,
        reserve_percentage=10,
        required_capacity=round(forecast * 1.1),
        source=source,
        source_reference="Planning!L13",
        source_identity=source_identity,
    )
    with db_session() as conn:
        coverage_repository.persist_imported_requirements(
            conn, [requirement], organization_id=ORG, now=utc_now_iso()
        )


def _item(body: dict, cycle: str, segment: str | None) -> dict:
    return next(
        item for item in body["items"]
        if item["cycle"] == cycle and item["segment"] == segment
    )


def test_create_three_manual_buckets_and_round_half_up():
    response = _save([
        {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76},
        {"cycle": "SAME_DAY", "segment": "A", "forecast_routes": 20},
        {"cycle": "SAME_DAY", "segment": "B_C", "forecast_routes": 18},
    ])
    assert response.status_code == 200, response.text
    body = response.json()
    assert _item(body, "NEXT_DAY", None)["required_capacity"] == 84
    assert _item(body, "SAME_DAY", "A")["required_capacity"] == 22
    assert _item(body, "SAME_DAY", "B_C")["required_capacity"] == 20
    assert {
        _item(body, "NEXT_DAY", None)["source"],
        _item(body, "SAME_DAY", "A")["source"],
        _item(body, "SAME_DAY", "B_C")["source"],
    } == {"MANUAL_PLANNING_INPUT"}


def test_partial_update_preserves_other_buckets_and_zero_is_real_forecast():
    first = _save([
        {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76},
        {"cycle": "SAME_DAY", "segment": "A", "forecast_routes": 20},
    ])
    second = _save(
        [{"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 0}],
        first.json()["fingerprint"],
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert _item(body, "NEXT_DAY", None)["forecast_routes"] == 0
    assert _item(body, "NEXT_DAY", None)["coverage_status"] != "NO_FORECAST"
    assert _item(body, "SAME_DAY", "A")["forecast_routes"] == 20
    assert _item(body, "SAME_DAY", "B_C")["coverage_status"] == "NO_FORECAST"


def test_invalid_negative_duplicate_and_bucket_are_rejected():
    fingerprint = _coverage()["fingerprint"]
    negative = client.put(
        f"{BASE}/{DAY}",
        json={
            "expected_fingerprint": fingerprint,
            "requirements": [{
                "cycle": "NEXT_DAY", "segment": None, "forecast_routes": -1,
            }],
        },
    )
    duplicate = client.put(
        f"{BASE}/{DAY}",
        json={
            "expected_fingerprint": fingerprint,
            "requirements": [
                {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 1},
                {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 2},
            ],
        },
    )
    invalid_bucket = client.put(
        f"{BASE}/{DAY}",
        json={
            "expected_fingerprint": fingerprint,
            "requirements": [{
                "cycle": "NEXT_DAY", "segment": "A", "forecast_routes": 1,
            }],
        },
    )
    assert negative.status_code == 422
    assert duplicate.status_code == 422
    assert invalid_bucket.status_code == 422


def test_manual_value_overrides_import_and_later_import_cannot_hide_it():
    _imported(240, source_identity="import:first")
    imported = _coverage()
    assert _item(imported, "NEXT_DAY", None)["forecast_routes"] == 240
    manual = _save(
        [{"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76}],
        imported["fingerprint"],
    )
    assert manual.status_code == 200
    _imported(300, source_identity="import:later")
    current = _coverage()
    item = _item(current, "NEXT_DAY", None)
    assert item["forecast_routes"] == 76
    assert item["source"] == "MANUAL_PLANNING_INPUT"
    with db_session() as conn:
        import_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ? AND source = 'IMPORT'
            """,
            (ORG,),
        ).fetchone()["total"]
    assert import_count == 2


def test_explicit_manual_save_of_same_imported_value_changes_provenance_only():
    _imported(76, source_identity="import:same-value")
    imported = _coverage()
    saved = _save(
        [{"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76}],
        imported["fingerprint"],
    )
    assert saved.status_code == 200
    item = _item(saved.json(), "NEXT_DAY", None)
    assert item["forecast_routes"] == 76
    assert item["source"] == "MANUAL_PLANNING_INPUT"


def test_stale_fingerprint_returns_409_without_overwrite():
    stale = _coverage()["fingerprint"]
    first = _save(
        [{"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76}],
        stale,
    )
    assert first.status_code == 200
    conflict = _save(
        [{"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 78}],
        stale,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "MANUAL_COVERAGE_STALE"
    assert _item(_coverage(), "NEXT_DAY", None)["forecast_routes"] == 76


def test_atomic_multi_bucket_rolls_back_on_repository_failure(monkeypatch):
    original = manual_coverage_repository.save_manual_requirements

    def fail_after_first(conn, **kwargs):
        first = {**kwargs, "requirements": kwargs["requirements"][:1]}
        original(conn, **first)
        raise RuntimeError("forced failure")

    monkeypatch.setattr(
        manual_coverage_repository, "save_manual_requirements", fail_after_first
    )
    with pytest.raises(RuntimeError, match="forced failure"):
        manual_coverage_service.save_daily_forecast(
            organization_id=ORG,
            operational_date=DAY,
            requirements=[
                {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76},
                {"cycle": "SAME_DAY", "segment": "A", "forecast_routes": 20},
            ],
            expected_fingerprint=_coverage()["fingerprint"],
            actor="dispatcher@example.test",
        )
    assert _coverage()["summary"]["forecast_available_buckets"] == 0
    with db_session() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_changes"
        ).fetchone()["total"] == 0


def test_audit_records_actor_old_new_bucket_and_organization():
    _imported(240, source_identity="import:audit")
    response = _save([
        {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76},
    ])
    assert response.status_code == 200
    with db_session() as conn:
        audit = conn.execute(
            """
            SELECT * FROM workforce_changes
            WHERE reason = 'planning_forecast_manual_updated'
            """
        ).fetchone()
    assert audit is not None
    assert audit["actor"] == "harness@example.test"
    assert audit["organization_id"] == ORG
    assert '"forecast_routes": 240' in audit["before_value"]
    assert '"forecast_routes": 76' in audit["after_value"]


def test_organization_isolation_keeps_same_day_independent():
    other_before = _coverage("other-organization")
    manual_coverage_service.save_daily_forecast(
        organization_id="other-organization",
        operational_date=DAY,
        requirements=[{
            "cycle": "NEXT_DAY", "segment": None, "forecast_routes": 12,
        }],
        expected_fingerprint=other_before["fingerprint"],
        actor="other@example.test",
    )
    assert _item(_coverage("other-organization"), "NEXT_DAY", None)[
        "forecast_routes"
    ] == 12
    assert _item(_coverage(), "NEXT_DAY", None)["forecast_routes"] is None


def test_planning_workforce_and_dsp_read_the_same_manual_source_of_truth():
    saved = _save([
        {"cycle": "NEXT_DAY", "segment": None, "forecast_routes": 76},
        {"cycle": "SAME_DAY", "segment": "A", "forecast_routes": 20},
        {"cycle": "SAME_DAY", "segment": "B_C", "forecast_routes": 18},
    ])
    assert saved.status_code == 200
    planning = client.get(
        "/api/planning/operations", params={"operation_date": DAY}
    )
    dsp = client.get(
        "/api/dsp-workspace/daily-snapshot", params={"operation_date": DAY}
    )
    workforce = client.get(
        BASE, params={"date_from": DAY, "date_to": DAY}
    )
    assert planning.status_code == dsp.status_code == workforce.status_code == 200
    assert planning.json()["summary"]["routes_forecast"] == 114
    assert planning.json()["summary"]["requirement"] == 126
    assert planning.json()["coverage"]["fingerprint"] == workforce.json()[
        "fingerprint"
    ]
    dsp_next = next(
        item for item in dsp.json()["coverage"]
        if item["cycle"] == "NEXT_DAY" and item["segment"] is None
    )
    assert (dsp_next["forecast"], dsp_next["requirement"]) == (76, 84)

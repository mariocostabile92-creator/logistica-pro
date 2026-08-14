from starlette.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.api import planning_workforce_bridge as bridge_module


DAY = "2026-08-14"
ORG = "test-organization"
NOW = f"{DAY}T08:00:00+00:00"
client = TestClient(app)


def _member(
    identifier: str,
    *,
    organization_id: str = ORG,
    cycle: str = "NEXT_DAY",
    shift_code: str | None = "C1",
    status: str = "scheduled",
    availability: bool = True,
    reserve: bool = False,
    operation_date: str = DAY,
) -> int:
    with db_session() as conn:
        member_id = int(conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, first_name,
                last_name, role, employment_type, station, capabilities, active,
                source_reference, operational_cycle, is_reserve, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '', 'driver', 'full_time', 'DLO2', '[]', 1,
                      'planning-bridge-test', ?, ?, ?, ?)
            """,
            (
                organization_id,
                identifier,
                identifier,
                identifier,
                cycle,
                int(reserve),
                NOW,
                NOW,
            ),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                shift_code, operational_activity, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, ?, ?, ?, 'delivery', 'planning-bridge-test',
                      'manual', ?, ?)
            """,
            (
                member_id,
                operation_date,
                status,
                int(availability),
                shift_code,
                NOW,
                organization_id,
            ),
        )
    return member_id


def _requirement(
    cycle: str,
    segment: str | None,
    forecast: int,
    requirement: int,
    *,
    organization_id: str = ORG,
    operation_date: str = DAY,
) -> None:
    segment_key = segment or ""
    identity = f"planning:{organization_id}:{operation_date}:{cycle}:{segment_key}"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_daily_coverage_requirements (
                organization_id, operational_date, station, station_key,
                operational_cycle, coverage_segment, forecast_routes,
                reserve_percentage, required_capacity, source,
                source_reference, source_identity, created_at, updated_at
            ) VALUES (?, ?, NULL, '', ?, ?, ?, 10, ?, 'MANUAL',
                      'planning-bridge-test', ?, ?, ?)
            """,
            (
                organization_id,
                operation_date,
                cycle,
                segment_key,
                forecast,
                requirement,
                identity,
                NOW,
                NOW,
            ),
        )


def _snapshot(operation_date: str = DAY) -> dict:
    response = client.get(
        "/api/planning/operations",
        params={"operation_date": operation_date},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_planning_reads_forecast_requirement_and_assignments_from_coverage():
    _member("ND-1", cycle="NEXT_DAY", shift_code="C1")
    _member("SA-1", cycle="SAME_DAY", shift_code="SA")
    _member("SB-1", cycle="SAME_DAY", shift_code="SB")
    _requirement("NEXT_DAY", None, 10, 11)
    _requirement("SAME_DAY", "A", 3, 4)
    _requirement("SAME_DAY", "B_C", 4, 5)

    payload = _snapshot()
    items = {
        (item["cycle"], item["segment"]): item
        for item in payload["coverage"]["items"]
    }
    assert items[("NEXT_DAY", None)]["forecast"] == 10
    assert items[("NEXT_DAY", None)]["requirement"] == 11
    assert items[("NEXT_DAY", None)]["assigned"] == 1
    assert items[("SAME_DAY", "A")]["assigned"] == 1
    assert items[("SAME_DAY", "B_C")]["assigned"] == 1
    assert payload["summary"]["routes_forecast"] == 17
    assert payload["summary"]["requirement"] == 20
    assert payload["summary"]["requirement_gap"] == 17


def test_planning_reuses_dsp_semantics_for_rest_absence_and_reserve():
    _member("PLANNED", reserve=True)
    _member("REST", status="rest", availability=True)
    _member("HOLIDAY", status="holiday", availability=False)
    _member("SICK", status="sickness", availability=False)

    _requirement("NEXT_DAY", None, 2, 3)
    payload = _snapshot()
    summary = payload["workforce"]["summary"]
    assert summary["planned"] == 1
    assert summary["available"] == 1
    assert summary["absent"] == 2
    assert summary["reserves"] == 1
    assert summary["next_day"] == 1
    next_day = next(
        item for item in payload["coverage"]["items"]
        if item["cycle"] == "NEXT_DAY" and item["segment"] is None
    )
    assert next_day["assigned"] == 1


def test_missing_route_and_vehicle_sources_are_not_false_zeroes():
    _member("PLANNED")
    payload = _snapshot()
    assert payload["route_data_available"] is False
    assert payload["vehicle_assignments_available"] is False
    assert payload["summary"]["routes_definitive"] is None
    assert payload["summary"]["vehicles_assigned"] is None
    assert payload["summary"]["conflicts"] is None
    assert payload["lifecycle"]["state"] == "routes_missing"
    assert payload["lifecycle"]["disabled_reason"]


def test_selected_operational_date_does_not_fall_back_to_another_day():
    _member("TODAY")
    _requirement("NEXT_DAY", None, 8, 9)
    other = _snapshot("2026-08-15")
    assert other["operation_date"] == "2026-08-15"
    assert other["workforce"]["summary"]["planned"] == 0
    assert other["coverage"]["available"] is False
    assert other["summary"]["routes_forecast"] is None


def test_planning_bridge_is_organization_scoped():
    _member("OTHER", organization_id="other-organization")
    _requirement(
        "NEXT_DAY",
        None,
        99,
        109,
        organization_id="other-organization",
    )
    payload = _snapshot()
    assert payload["workforce"]["summary"]["total"] == 0
    assert payload["workforce"]["summary"]["planned"] == 0
    assert payload["coverage"]["available"] is False


def test_planning_and_dsp_have_identical_workforce_and_coverage_projection():
    _member("ND-1", cycle="NEXT_DAY", shift_code="C1")
    _member("ABSENT", status="leave", availability=False)
    _requirement("NEXT_DAY", None, 2, 3)

    planning = _snapshot()
    response = client.get(
        "/api/dsp-workspace/daily-snapshot",
        params={"operation_date": DAY},
    )
    assert response.status_code == 200, response.text
    dsp = response.json()
    assert planning["workforce"]["summary"]["planned"] == dsp["counts"]["driver_planned_count"]
    assert planning["workforce"]["summary"]["absent"] == dsp["counts"]["driver_absent_count"]
    assert planning["coverage"]["items"] == dsp["coverage"]


def test_bridge_invokes_each_shared_date_scoped_reader_once(monkeypatch):
    _member("ND-1")
    calls = {"workforce": 0, "coverage": 0}
    original_workforce = bridge_module.workforce_daily_projection
    original_coverage = bridge_module.daily_coverage

    def workforce_spy(*args, **kwargs):
        calls["workforce"] += 1
        return original_workforce(*args, **kwargs)

    def coverage_spy(*args, **kwargs):
        calls["coverage"] += 1
        return original_coverage(*args, **kwargs)

    monkeypatch.setattr(bridge_module, "workforce_daily_projection", workforce_spy)
    monkeypatch.setattr(bridge_module, "daily_coverage", coverage_spy)
    bridge_module.planning_workforce_input(
        operation_date=DAY,
        organization_id=ORG,
    )
    assert calls == {"workforce": 1, "coverage": 1}

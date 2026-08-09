from pathlib import Path

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.drivers_read_service import (
    get_drivers,
    get_latest_drivers,
)
from app.plugins.dsp_quality.application.history_service import (
    get_scorecard_history,
)
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.metrics_read_service import (
    get_latest_metrics,
    get_metrics,
)
from app.plugins.dsp_quality.application.read_service import (
    get_latest_scorecard,
    get_scorecard,
)
from app.plugins.dsp_quality.application.reconciliation_service import (
    put_mapping,
    reconciliation_state,
)


FIXTURE = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
TRANSPORTER = "A10GSCDE4XETEE"


def document(week: int, *, station: str = "DLO2", dsp: str = "PROF"):
    base = QualityImportDocument.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={
            "reported_week": week,
            "reported_year": 2025,
            "station": station,
            "dsp_identifier": dsp,
        }),
        "revision": base.revision.model_copy(update={
            "source_filename": f"{dsp}-{station}-Week-{week}.pdf",
            "raw_period_label": f"Week {week} - 2025",
        }),
    })


def persist(org: str, week: int, *, station: str = "DLO2", dsp: str = "PROF", content: bytes | None = None):
    return ingest_quality_document(
        organization_id=org,
        document=document(week, station=station, dsp=dsp),
        source_content=content or f"{org}-{dsp}-{station}-{week}".encode(),
        imported_by="q9-test",
    )


def member(org: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
              external_identifier, display_name, station, employment_type,
              capabilities, active, source_reference, created_at, updated_at,
              organization_id
            ) VALUES ('WF-Q9', 'Mario Rossi', 'DLO2', 'full_time', '[]', 1,
              'q9-test', '2026-08-09T10:00:00+00:00',
              '2026-08-09T10:00:00+00:00', ?)
            """,
            (org,),
        )
        return int(cursor.lastrowid)


def test_history_is_compact_and_orders_by_period_not_import_time():
    week45 = persist("q9-org", 45)
    week47 = persist("q9-org", 47)
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_scorecard_versions SET imported_at = '2030-01-01T00:00:00Z' WHERE scorecard_id = ?",
            (week45.scorecard_id,),
        )
        conn.execute(
            "UPDATE dsp_quality_scorecard_versions SET imported_at = '2020-01-01T00:00:00Z' WHERE scorecard_id = ?",
            (week47.scorecard_id,),
        )

    history = get_scorecard_history("q9-org")

    assert [item.reported_week for item in history.items] == [47, 45]
    assert history.items[0].scorecard_id == week47.scorecard_id
    assert history.items[0].revision_count == 1
    assert not hasattr(history.items[0], "metrics")


def test_history_keeps_multi_station_timelines_distinct():
    persist("q9-org", 47, station="DLO2", dsp="PROF")
    persist("q9-org", 47, station="DLO3", dsp="ALT")
    items = get_scorecard_history("q9-org").items
    assert {(item.dsp_identifier, item.station) for item in items} == {
        ("PROF", "DLO2"), ("ALT", "DLO3"),
    }


def test_detail_uses_active_revision_and_revision_count_without_duplicate_week():
    created = persist("q9-org", 45, content=b"q9-week45-v1")
    no_op = persist("q9-org", 45, content=b"q9-week45-v1")
    revised = persist("q9-org", 45, content=b"q9-week45-v2")

    history = get_scorecard_history("q9-org")
    detail = get_scorecard("q9-org", created.scorecard_id)

    assert no_op.idempotent is True
    assert revised.scorecard_id == created.scorecard_id
    assert len(history.items) == 1
    assert history.items[0].revision_count == 2
    assert detail.scorecard.revision_id == revised.active_revision_id
    assert detail.revision.active_number == 2
    assert detail.revision.revision_count == 2


def test_metrics_selected_period_uses_only_earlier_same_timeline_with_gap():
    week45 = persist("q9-org", 45)
    week47 = persist("q9-org", 47)

    current47 = get_metrics("q9-org", week47.scorecard_id)
    current45 = get_metrics("q9-org", week45.scorecard_id)

    assert current47.current_period.week == 47
    assert current47.previous_period.week == 45
    assert current45.current_period.week == 45
    assert current45.previous_available is False
    assert current45.previous_period is None


def test_drivers_selected_period_has_gap_semantics_and_no_future_previous():
    week45 = persist("q9-org", 45)
    week47 = persist("q9-org", 47)
    selected47 = get_drivers("q9-org", week47.scorecard_id)
    selected45 = get_drivers("q9-org", week45.scorecard_id)
    assert selected47.previous_period.week == 45
    assert selected45.previous_available is False


def test_previous_never_crosses_dsp_or_station_timeline():
    persist("q9-org", 44, station="DLO2", dsp="PROF")
    persist("q9-org", 46, station="DLO3", dsp="ALT")
    current = persist("q9-org", 47, station="DLO2", dsp="PROF")

    metrics = get_metrics("q9-org", current.scorecard_id)
    drivers = get_drivers("q9-org", current.scorecard_id)

    assert metrics.previous_period.week == drivers.previous_period.week == 44


def test_mapping_is_global_and_reconciliation_uses_selected_scorecard():
    week45 = persist("q9-org", 45)
    week47 = persist("q9-org", 47)
    workforce_id = member("q9-org")
    put_mapping(
        organization_id="q9-org",
        external_id=TRANSPORTER,
        workforce_member_id=workforce_id,
        actor="q9-admin",
        expected_updated_at=None,
        scorecard_id=week45.scorecard_id,
    )

    old = reconciliation_state("q9-org", week45.scorecard_id)
    new = reconciliation_state("q9-org", week47.scorecard_id)
    assert old.scorecard_id == week45.scorecard_id
    assert old.week == 45 and new.week == 47
    assert old.summary.matched == 1 and new.summary.matched == 1
    assert get_drivers("q9-org", week45.scorecard_id).rows[0].workforce_display_name == "Mario Rossi"
    assert get_drivers("q9-org", week47.scorecard_id).rows[0].workforce_display_name == "Mario Rossi"
    assert get_scorecard("q9-org", week45.scorecard_id).counts.mapped_transporters == 1
    assert get_scorecard("q9-org", week47.scorecard_id).counts.mapped_transporters == 1


def test_history_and_selected_reads_are_organization_isolated():
    own = persist("q9-org-a", 45)
    foreign = persist("q9-org-b", 47)
    assert [item.scorecard_id for item in get_scorecard_history("q9-org-a").items] == [own.scorecard_id]
    assert get_scorecard("q9-org-a", foreign.scorecard_id).available is False
    assert get_metrics("q9-org-a", foreign.scorecard_id).available is False
    assert get_drivers("q9-org-a", foreign.scorecard_id).available is False


def test_latest_aliases_remain_period_latest():
    persist("q9-org", 45)
    latest = persist("q9-org", 47)
    assert get_latest_scorecard("q9-org").scorecard.id == latest.scorecard_id
    assert get_latest_metrics("q9-org").current_period.week == 47
    assert get_latest_drivers("q9-org").current_period.week == 47


def test_history_and_selected_endpoints_are_scoped_and_read_only():
    selected = persist("test-organization", 45)
    foreign = persist("q9-foreign", 47)
    client = TestClient(app)
    with db_session() as conn:
        before = conn.execute("SELECT COUNT(*) count FROM dsp_quality_scorecards").fetchone()["count"]

    history = client.get("/api/dsp-quality/scorecards")
    detail = client.get(f"/api/dsp-quality/scorecards/{selected.scorecard_id}")
    metrics = client.get(f"/api/dsp-quality/scorecards/{selected.scorecard_id}/metrics")
    drivers = client.get(f"/api/dsp-quality/scorecards/{selected.scorecard_id}/drivers")
    blocked = client.get(f"/api/dsp-quality/scorecards/{foreign.scorecard_id}")

    assert history.status_code == detail.status_code == metrics.status_code == drivers.status_code == 200
    assert blocked.status_code == 404
    assert history.json()["items"][0]["scorecard_id"] == selected.scorecard_id
    with db_session() as conn:
        after = conn.execute("SELECT COUNT(*) count FROM dsp_quality_scorecards").fetchone()["count"]
    assert after == before


def test_reconciliation_endpoint_accepts_canonical_selected_scorecard():
    selected = persist("test-organization", 45)
    client = TestClient(app)
    response = client.get(
        "/api/dsp-quality/transporter-mappings/reconciliation",
        params={"scorecard_id": selected.scorecard_id},
    )
    assert response.status_code == 200
    assert response.json()["scorecard_id"] == selected.scorecard_id
    assert response.json()["week"] == 45

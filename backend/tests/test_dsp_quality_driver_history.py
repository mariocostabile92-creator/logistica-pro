from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.driver_history_service import (
    get_driver_history,
)
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.mapping_service import (
    set_workforce_external_identity,
)
from app.plugins.dsp_quality.domain.models import QualityMappingStatus
from app.plugins.dsp_quality.infrastructure import driver_history_repository


FIXTURE = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
TRANSPORTER = "A10GSCDE4XETEE"


def _document(
    week: int,
    values: dict[str, str | None],
    *,
    station: str = "DLO2",
    dsp: str = "PROF",
) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )
    first = base.transporter_rows[0]
    metrics = [
        item.model_copy(update={"raw_value": values[item.metric_key]})
        if item.metric_key in values else item
        for item in first.metrics
    ]
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={
            "reported_week": week,
            "reported_year": 2025,
            "station": station,
            "dsp_identifier": dsp,
        }),
        "revision": base.revision.model_copy(update={
            "source_filename": f"history-{dsp}-{station}-{week}.pdf",
            "raw_period_label": f"Week {week} - 2025",
        }),
        "transporter_rows": [first.model_copy(update={"metrics": metrics})],
    })


def _persist(
    org: str,
    week: int,
    values: dict[str, str | None],
    *,
    station: str = "DLO2",
    dsp: str = "PROF",
    content: bytes | None = None,
):
    return ingest_quality_document(
        organization_id=org,
        document=_document(week, values, station=station, dsp=dsp),
        source_content=content or f"{org}-{dsp}-{station}-{week}-{values}".encode(),
        imported_by="q11-test",
    )


def _metric(entry, key: str):
    return next(item for item in entry.metrics if item.metric_key == key)


def test_non_consecutive_timeline_and_direction_adjusted_comparisons():
    for week, pod, cdf in [
        (42, "99.5%", "5000"),
        (43, "99.0%", "4500"),
        (45, "98.2%", "4000"),
        (46, "97.5%", "3200"),
    ]:
        _persist("q11-trends", week, {
            "photo_on_delivery": pod,
            "customer_delivery_feedback_dpmo": cdf,
            "customer_escalations_count": "1" if week == 46 else "0",
        })

    result = get_driver_history("q11-trends", TRANSPORTER)

    assert [item.week for item in result.timeline] == [42, 43, 45, 46]
    assert _metric(result.timeline[-1], "photo_on_delivery").comparison == "WORSENED"
    assert _metric(result.timeline[-1], "customer_delivery_feedback_dpmo").comparison == "IMPROVED"
    assert _metric(result.timeline[-1], "photo_on_delivery").recurring is True
    assert result.summary.recurring_worsening_metrics[0].metric_key == "photo_on_delivery"
    assert any(
        item.metric_key == "customer_delivery_feedback_dpmo"
        for item in result.summary.recurring_improving_metrics
    )
    assert result.timeline[-1].customer_escalations == 1
    assert result.summary.recent_customer_escalations == 1


def test_recovery_requires_two_improvements_after_negative_sequence():
    for week, value in [(40, 100), (41, 90), (42, 80), (43, 90), (44, 100)]:
        _persist("q11-recovery", week, {"photo_on_delivery": f"{value}%"})

    metric = _metric(
        get_driver_history("q11-recovery", TRANSPORTER).timeline[-1],
        "photo_on_delivery",
    )

    assert metric.consecutive_improving_comparisons == 2
    assert metric.recovery is True


def test_unchanged_missing_and_delivered_volume_only_are_explicit():
    _persist("q11-gaps", 41, {
        "delivery_completion_rate": "97%",
        "photo_on_delivery": "99%",
        "delivered": "100",
    })
    _persist("q11-gaps", 43, {
        "delivery_completion_rate": "97%",
        "photo_on_delivery": None,
        "delivered": "120",
    })
    latest = get_driver_history("q11-gaps", TRANSPORTER).timeline[-1]

    assert _metric(latest, "delivery_completion_rate").comparison == "UNCHANGED"
    assert _metric(latest, "photo_on_delivery").comparison == "NOT_COMPARABLE"
    assert _metric(latest, "photo_on_delivery").value.numeric_value is None
    assert _metric(latest, "delivered").comparison == "NOT_COMPARABLE"
    assert _metric(latest, "delivered").direction == "NO_DIRECTION"
    assert all(metric.status == "NO_DRIVER_STANDARD" for metric in latest.metrics)


def test_focus_history_and_q10_status_are_reconstructed_per_week():
    _persist("q11-focus", 44, {
        "photo_on_delivery": "99%",
        "delivery_completion_rate": "99%",
    })
    _persist("q11-focus", 46, {
        "photo_on_delivery": "97%",
        "delivery_completion_rate": "96%",
    })
    result = get_driver_history("q11-focus", TRANSPORTER)

    assert result.timeline[0].weekly_status == "SENZA_STORICO"
    assert result.timeline[1].weekly_status == "DA_ATTENZIONARE"
    assert {item.metric_key for item in result.timeline[1].weekly_focus} == {
        "photo_on_delivery", "delivery_completion_rate",
    }
    assert result.summary.current_focus == result.timeline[1].weekly_focus


def test_workforce_mapping_is_display_only_and_transporter_remains_history_key():
    _persist("q11-name", 45, {"photo_on_delivery": "99%"})
    _persist("q11-name", 46, {"photo_on_delivery": "98%"})
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
              external_identifier, display_name, capabilities, active,
              source_reference, created_at, updated_at, organization_id
            ) VALUES ('WF-Q11', 'Mario Rossi', '[]', 1, 'q11-test',
              '2026-08-12T10:00:00Z', '2026-08-12T10:00:00Z', ?)
            """,
            ("q11-name",),
        )
        member_id = int(cursor.lastrowid)
    set_workforce_external_identity(
        organization_id="q11-name",
        external_id=TRANSPORTER,
        status=QualityMappingStatus.MATCHED,
        workforce_member_id=member_id,
        actor="q11-test",
    )

    result = get_driver_history("q11-name", TRANSPORTER)

    assert result.transporter_external_id == TRANSPORTER
    assert result.workforce_display_name == "Mario Rossi"
    assert result.mapping_status == "MATCHED"
    assert all(
        result.transporter_external_id == TRANSPORTER for _ in result.timeline
    )


def test_revision_organization_and_station_semantics_are_isolated():
    selected = _persist(
        "q11-scope", 45, {"photo_on_delivery": "99%"}, content=b"scope-v1"
    )
    _persist(
        "q11-scope", 45, {"photo_on_delivery": "97%"}, content=b"scope-v2"
    )
    _persist("q11-scope", 46, {"photo_on_delivery": "10%"}, station="DLO3")
    _persist("q11-other", 46, {"photo_on_delivery": "5%"})

    result = get_driver_history(
        "q11-scope", TRANSPORTER, scorecard_id=selected.scorecard_id
    )

    assert len(result.timeline) == 1
    assert result.timeline[0].scorecard_id == selected.scorecard_id
    assert result.timeline[0].revision_id != ""
    assert _metric(result.timeline[0], "photo_on_delivery").value.numeric_value == 97
    assert result.station == "DLO2"


def test_repository_query_count_is_constant_not_per_week(monkeypatch):
    for week in range(40, 46):
        _persist("q11-query", week, {"photo_on_delivery": f"{90 + week - 40}%"})

    original = driver_history_repository.db_session
    calls = []

    @contextmanager
    def counted_session():
        with original() as connection:
            class ConnectionProxy:
                def execute(self, *args, **kwargs):
                    calls.append(args[0])
                    return connection.execute(*args, **kwargs)

            yield ConnectionProxy()

    monkeypatch.setattr(driver_history_repository, "db_session", counted_session)
    result = get_driver_history("q11-query", TRANSPORTER)

    assert result.summary.weeks_available == 6
    assert len(calls) == 3


def test_history_endpoint_uses_session_organization_and_selected_context():
    selected = _persist(
        "test-organization", 46,
        {"photo_on_delivery": "98%", "customer_escalations_count": "1"},
    )
    _persist("other-organization", 47, {"photo_on_delivery": "1%"})
    client = TestClient(app)

    response = client.get(
        f"/api/dsp-quality/drivers/{TRANSPORTER}/history",
        params={"scorecard_id": selected.scorecard_id, "limit": 12},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["anchor_scorecard_id"] == selected.scorecard_id
    assert payload["summary"]["weeks_available"] == 1
    assert payload["timeline"][0]["customer_escalations"] == 1

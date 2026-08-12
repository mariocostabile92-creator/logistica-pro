from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plugins.dsp_quality.application.followup_models import (
    QualityFollowupCreateRequest,
)
from app.plugins.dsp_quality.application.followup_service import (
    close_followup,
    create_followup,
    get_followup,
    list_followups,
)
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.infrastructure.followup_repository import list_events


FIXTURE = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
TRANSPORTER = "A10GSCDE4XETEE"


def _document(
    week: int,
    values: dict[str, str | None],
    *,
    include_driver: bool = True,
    dsp: str = "PROF",
    station: str = "DLO2",
) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    first = base.transporter_rows[0]
    metrics = [
        item.model_copy(update={"raw_value": values[item.metric_key]})
        if item.metric_key in values else item
        for item in first.metrics
    ]
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={
            "reported_week": week,
            "reported_year": 2026,
            "dsp_identifier": dsp,
            "station": station,
        }),
        "revision": base.revision.model_copy(update={
            "source_filename": f"followup-{week}-{dsp}-{station}.pdf",
            "raw_period_label": f"Week {week} - 2026",
        }),
        "transporter_rows": [first.model_copy(update={"metrics": metrics})]
        if include_driver else [],
    })


def _persist(
    organization_id: str,
    week: int,
    values: dict[str, str | None],
    **kwargs,
):
    return ingest_quality_document(
        organization_id=organization_id,
        document=_document(week, values, **kwargs),
        source_content=f"{organization_id}-{week}-{values}-{kwargs}".encode(),
        imported_by="q12-test",
    )


def _create(organization_id: str, scorecard_id: str, metric_key: str):
    return create_followup(
        organization_id,
        QualityFollowupCreateRequest(
            transporter_external_id=TRANSPORTER,
            scorecard_id=scorecard_id,
            metric_key=metric_key,
            note="Confronto operativo con il driver.",
        ),
        actor="manager-q12",
    )


def test_create_persists_real_metric_baseline_and_audit():
    baseline = _persist("q12-create", 46, {"delivery_completion_rate": "98.04%"})

    result = _create("q12-create", baseline.scorecard_id, "delivery_completion_rate")

    assert result.created is True
    assert result.item.baseline.week == 46
    assert result.item.baseline.value == 98.04
    assert result.item.baseline_direction == "HIGHER_IS_BETTER"
    assert result.item.status == "OPEN"
    events = list_events("q12-create", result.item.id)
    assert [item["event_type"] for item in events] == ["quality_followup_created"]
    assert "Confronto operativo" not in (events[0]["details"] or "")


def test_duplicate_active_followup_returns_existing_without_second_event():
    baseline = _persist("q12-duplicate", 46, {"photo_on_delivery": "98%"})
    first = _create("q12-duplicate", baseline.scorecard_id, "photo_on_delivery")
    second = _create("q12-duplicate", baseline.scorecard_id, "photo_on_delivery")

    assert second.created is False
    assert second.item.id == first.item.id
    assert len(list_events("q12-duplicate", first.item.id)) == 1


@pytest.mark.parametrize(
    ("metric_key", "baseline_value", "review_value", "expected"),
    [
        ("delivery_completion_rate", "98%", "99%", "IMPROVED"),
        ("delivery_completion_rate", "98%", "97%", "WORSENED"),
        ("customer_delivery_feedback_dpmo", "6000", "5000", "IMPROVED"),
        ("customer_delivery_feedback_dpmo", "6000", "7000", "WORSENED"),
        ("photo_on_delivery", "98%", "98%", "UNCHANGED"),
    ],
)
def test_review_direction_logic(metric_key, baseline_value, review_value, expected):
    organization_id = f"q12-direction-{expected}-{metric_key}"
    baseline = _persist(organization_id, 46, {metric_key: baseline_value})
    created = _create(organization_id, baseline.scorecard_id, metric_key)
    _persist(organization_id, 47, {metric_key: review_value})

    reviewed = get_followup(organization_id, created.item.id)

    assert reviewed.status == expected
    assert reviewed.review.result == expected
    assert reviewed.review.state == "COMPARABLE"
    assert reviewed.review.period.week == 47
    assert [item["event_type"] for item in list_events(organization_id, created.item.id)] == [
        "quality_followup_created", "quality_followup_reviewed"
    ]


def test_first_real_non_consecutive_scorecard_is_used():
    baseline = _persist("q12-gap", 46, {"delivery_completion_rate": "98%"})
    created = _create("q12-gap", baseline.scorecard_id, "delivery_completion_rate")
    _persist("q12-gap", 48, {"delivery_completion_rate": "99%"})

    reviewed = get_followup("q12-gap", created.item.id)

    assert reviewed.status == "IMPROVED"
    assert reviewed.review.period.week == 48


def test_missing_metric_and_missing_driver_remain_open_on_first_next_scorecard():
    metric_baseline = _persist("q12-missing-metric", 46, {"photo_on_delivery": "98%"})
    metric_followup = _create("q12-missing-metric", metric_baseline.scorecard_id, "photo_on_delivery")
    _persist("q12-missing-metric", 47, {"photo_on_delivery": None})
    _persist("q12-missing-metric", 48, {"photo_on_delivery": "100%"})
    missing_metric = get_followup("q12-missing-metric", metric_followup.item.id)

    driver_baseline = _persist("q12-missing-driver", 46, {"photo_on_delivery": "98%"})
    driver_followup = _create("q12-missing-driver", driver_baseline.scorecard_id, "photo_on_delivery")
    _persist("q12-missing-driver", 47, {}, include_driver=False)
    missing_driver = get_followup("q12-missing-driver", driver_followup.item.id)

    assert missing_metric.status == "OPEN"
    assert missing_metric.review.state == "MISSING_METRIC"
    assert missing_metric.review.period.week == 47
    assert "Dati insufficienti" in missing_metric.review.message
    assert missing_driver.status == "OPEN"
    assert missing_driver.review.state == "MISSING_DRIVER"
    assert "Driver non presente" in missing_driver.review.message


def test_delivered_is_rejected_and_no_record_is_created():
    baseline = _persist("q12-delivered", 46, {"delivered": "120"})

    with pytest.raises(ValueError, match="volume"):
        _create("q12-delivered", baseline.scorecard_id, "delivered")

    assert list_followups("q12-delivered").items == []


def test_close_requires_review_is_manual_and_is_immutable():
    baseline = _persist("q12-close", 46, {"delivery_completion_rate": "98%"})
    created = _create("q12-close", baseline.scorecard_id, "delivery_completion_rate")
    with pytest.raises(RuntimeError, match="dopo una verifica"):
        close_followup("q12-close", created.item.id, actor="manager", note=None)
    _persist("q12-close", 47, {"delivery_completion_rate": "99%"})
    assert get_followup("q12-close", created.item.id).status == "IMPROVED"

    closed = close_followup(
        "q12-close", created.item.id, actor="manager", note="Verifica conclusa."
    )

    assert closed.status == "CLOSED"
    assert closed.review.result == "IMPROVED"
    assert closed.close_note == "Verifica conclusa."
    with pytest.raises(RuntimeError, match="già chiuso"):
        close_followup("q12-close", created.item.id, actor="manager", note=None)
    assert [item["event_type"] for item in list_events("q12-close", created.item.id)] == [
        "quality_followup_created", "quality_followup_reviewed", "quality_followup_closed"
    ]


def test_organization_isolation_for_read_create_and_close():
    baseline = _persist("q12-org-a", 46, {"photo_on_delivery": "98%"})
    created = _create("q12-org-a", baseline.scorecard_id, "photo_on_delivery")

    assert list_followups("q12-org-b").items == []
    with pytest.raises(LookupError):
        get_followup("q12-org-b", created.item.id)
    with pytest.raises(LookupError):
        close_followup("q12-org-b", created.item.id, actor="other", note=None)


def test_summary_filters_and_driver_history_data_are_consistent():
    baseline = _persist("q12-list", 46, {
        "photo_on_delivery": "98%",
        "customer_delivery_feedback_dpmo": "6000",
    })
    improved = _create("q12-list", baseline.scorecard_id, "photo_on_delivery")
    worsened = _create("q12-list", baseline.scorecard_id, "customer_delivery_feedback_dpmo")
    _persist("q12-list", 47, {
        "photo_on_delivery": "99%",
        "customer_delivery_feedback_dpmo": "7000",
    })

    result = list_followups("q12-list", transporter_external_id=TRANSPORTER)

    assert {item.status for item in result.items} == {"IMPROVED", "WORSENED"}
    assert result.summary.open == 2
    assert result.summary.improved == 1
    assert result.summary.worsened == 1
    assert list_followups("q12-list", status="IMPROVED").items[0].id == improved.item.id
    assert list_followups("q12-list", metric_key="customer_delivery_feedback_dpmo").items[0].id == worsened.item.id


def test_api_uses_session_organization_and_exposes_full_workflow():
    baseline = _persist("test-organization", 46, {"delivery_completion_rate": "98.04%"})
    client = TestClient(app)
    created = client.post("/api/dsp-quality/followups", json={
        "transporter_external_id": TRANSPORTER,
        "scorecard_id": baseline.scorecard_id,
        "metric_key": "delivery_completion_rate",
        "note": "Follow-up verificabile.",
    })
    assert created.status_code == 200
    followup_id = created.json()["item"]["id"]
    _persist("test-organization", 47, {"delivery_completion_rate": "99.02%"})

    listed = client.get("/api/dsp-quality/followups", params={
        "transporter_external_id": TRANSPORTER,
    })
    detail = client.get(f"/api/dsp-quality/followups/{followup_id}")
    closed = client.post(
        f"/api/dsp-quality/followups/{followup_id}/close",
        json={"note": "Azione verificata."},
    )

    assert listed.status_code == detail.status_code == closed.status_code == 200
    assert listed.json()["summary"]["improved"] == 1
    assert detail.json()["review"]["delta"] == pytest.approx(0.98)
    assert closed.json()["status"] == "CLOSED"


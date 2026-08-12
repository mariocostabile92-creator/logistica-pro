from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.dsp_quality.application.attention_read_service import get_attention
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document


FIXTURE = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"


def _document(week: int, values: dict[str, str | None]) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    first = base.transporter_rows[0]
    metrics = [
        item.model_copy(update={"raw_value": values[item.metric_key]})
        if item.metric_key in values else item
        for item in first.metrics
    ]
    dsp_metrics = [
        item.model_copy(update={"raw_value": values[item.metric_key]})
        if item.metric_key in values else item
        for item in base.dsp_metrics
    ]
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={
            "reported_week": week,
            "reported_year": 2025,
        }),
        "revision": base.revision.model_copy(update={
            "source_filename": f"attention-{week}.pdf",
            "raw_period_label": f"Week {week} - 2025",
        }),
        "transporter_rows": [first.model_copy(update={"metrics": metrics})],
        "dsp_metrics": dsp_metrics,
    })


def _persist(org: str, week: int, values: dict[str, str | None]):
    return ingest_quality_document(
        organization_id=org,
        document=_document(week, values),
        source_content=f"{org}-{week}-{values}".encode(),
        imported_by="attention-test",
    )


def test_driver_status_rules_are_exclusive_and_volume_is_not_classified():
    previous = {
        "delivery_completion_rate": "98%",
        "photo_on_delivery": "95%",
        "contact_compliance": "95%",
        "customer_escalations_count": "0",
    }
    current = {
        "delivered": "9999",
        "delivery_completion_rate": "96%",
        "photo_on_delivery": "93%",
        "contact_compliance": "97%",
        "customer_escalations_count": "0",
    }
    _persist("attention-rules", 45, previous)
    _persist("attention-rules", 47, current)

    model = get_attention("attention-rules")
    driver = model.drivers[0]

    assert driver.status == "DA_ATTENZIONARE"
    assert driver.worsened_metrics == 2
    assert driver.improved_metrics == 1
    assert all(item.metric_key != "delivered" for item in driver.focus)
    assert model.previous_period.week == 45
    assert model.summary.statuses.da_attenzionare == 1


def test_single_worsening_improving_stable_and_without_history_rules():
    _persist("attention-improve", 45, {
        "delivery_completion_rate": "95%",
        "photo_on_delivery": "90%",
    })
    _persist("attention-improve", 47, {
        "delivery_completion_rate": "96%",
        "photo_on_delivery": "90%",
    })
    assert get_attention("attention-improve").drivers[0].status == "IN_MIGLIORAMENTO"

    _persist("attention-single", 45, {"delivery_completion_rate": "98%"})
    _persist("attention-single", 47, {"delivery_completion_rate": "97%"})
    assert get_attention("attention-single").drivers[0].status == "DA_MIGLIORARE"

    _persist("attention-stable", 45, {"delivery_completion_rate": "97%"})
    _persist("attention-stable", 47, {"delivery_completion_rate": "97%"})
    assert get_attention("attention-stable").drivers[0].status == "STABILE"

    _persist("attention-new", 47, {"delivery_completion_rate": "97%"})
    assert get_attention("attention-new").drivers[0].status == "SENZA_STORICO"


def test_escalation_promotes_driver_even_without_previous_history():
    _persist("attention-escalation", 47, {"customer_escalations_count": "2"})

    driver = get_attention("attention-escalation").drivers[0]

    assert driver.status == "DA_ATTENZIONARE"
    assert driver.escalation_present is True
    assert driver.history_available is False
    assert driver.focus[0].metric_key == "customer_escalations_count"


def test_dsp_signals_use_persisted_standards_and_direction_adjusted_delta():
    _persist("attention-dsp", 45, {"delivery_completion_rate": "98%"})
    _persist("attention-dsp", 47, {"delivery_completion_rate": "96%"})

    signal = next(
        item for item in get_attention("attention-dsp").dsp_signals
        if item.metric_key == "delivery_completion_rate"
    )

    assert signal.standard_target is not None or signal.standard_minimum is not None
    assert signal.direction == "worsened"
    assert "persistito" in signal.reason


def test_selected_and_latest_attention_endpoints_are_organization_scoped():
    selected = _persist("test-organization", 47, {"customer_escalations_count": "1"})
    client = TestClient(app)

    latest = client.get("/api/dsp-quality/scorecards/latest/attention")
    explicit = client.get(
        f"/api/dsp-quality/scorecards/{selected.scorecard_id}/attention"
    )

    assert latest.status_code == 200
    assert explicit.status_code == 200
    assert latest.json()["summary"]["total_drivers"] == 1
    assert explicit.json()["drivers"][0]["status"] == "DA_ATTENZIONARE"

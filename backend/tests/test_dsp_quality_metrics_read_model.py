from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.metrics_read_service import get_latest_metrics


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"


def document(
    *,
    week: int = 47,
    year: int = 2025,
    dsp: str = "PROF",
    station: str = "DLO2",
    metric_values: dict[str, str] | None = None,
) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    identity = base.identity.model_copy(update={
        "reported_week": week,
        "reported_year": year,
        "dsp_identifier": dsp,
        "station": station,
    })
    revision = base.revision.model_copy(update={
        "source_filename": f"IT-{dsp}-{station}-Week{week}-DSP-Scorecard-3.0.pdf",
        "raw_period_label": f"Week {week} - {year}",
    })
    values = metric_values or {}
    metrics = [
        item.model_copy(update={"raw_value": values[item.metric_key]})
        if item.metric_key in values else item
        for item in base.dsp_metrics
    ]
    return base.model_copy(update={
        "identity": identity,
        "revision": revision,
        "dsp_metrics": metrics,
    })


def persist(
    organization_id: str = "quality-metrics-org",
    *,
    week: int = 47,
    year: int = 2025,
    dsp: str = "PROF",
    station: str = "DLO2",
    metric_values: dict[str, str] | None = None,
    content: bytes | None = None,
):
    return ingest_quality_document(
        organization_id=organization_id,
        document=document(
            week=week,
            year=year,
            dsp=dsp,
            station=station,
            metric_values=metric_values,
        ),
        source_content=content or f"{organization_id}-{dsp}-{station}-{year}-{week}".encode(),
        imported_by="quality-metrics-test",
    )


def metric(result, key: str):
    return next(item for item in result.metrics if item.metric_key == key)


def set_metric_and_standard(key: str, value: str, target: str | None, minimum: str | None):
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_metric_observations "
            "SET normalized_numeric_value = ?, raw_value = ?, value_state = 'PRESENT' "
            "WHERE metric_key = ?",
            (value, value, key),
        )
        conn.execute(
            "UPDATE dsp_quality_standard_rules SET target_value = ?, minimum_value = ? "
            "WHERE metric_key = ?",
            (target, minimum, key),
        )


def test_current_metric_observations_are_loaded_from_active_revision():
    persisted = persist()
    result = get_latest_metrics("quality-metrics-org")

    assert result.available is True
    assert result.metrics_available is True
    assert len(result.metrics) == len(document().dsp_metrics)
    assert metric(result, "photo_on_delivery").current.numeric_value == 97.64
    assert persisted.revision_id


def test_standard_target_minimum_and_version_are_from_current_revision():
    persist()
    item = metric(get_latest_metrics("quality-metrics-org"), "delivery_completion_rate")

    assert item.standard.target == 97.9
    assert item.standard.minimum == 97.0
    assert item.standard.raw_target == "97.9%"
    assert item.standard.standard_set.detected_source_version == "3.0"


@pytest.mark.parametrize(
    ("key", "value", "target", "minimum", "target_status", "minimum_status"),
    [
        ("delivery_completion_rate", "98", "97.9", "97", "TARGET_MET", "TARGET_MET"),
        ("delivery_completion_rate", "97.5", "97.9", "97", "BELOW_TARGET", "TARGET_MET"),
        ("delivery_completion_rate", "96", "97.9", "97", "BELOW_TARGET", "BELOW_MINIMUM"),
        ("delivery_success_conditions_dpmo", "400", "500", "780", "TARGET_MET", "TARGET_MET"),
        ("delivery_success_conditions_dpmo", "600", "500", "780", "BELOW_TARGET", "TARGET_MET"),
        ("delivery_success_conditions_dpmo", "900", "500", "780", "BELOW_TARGET", "BELOW_MINIMUM"),
    ],
)
def test_directional_standard_statuses(
    key, value, target, minimum, target_status, minimum_status,
):
    persist()
    set_metric_and_standard(key, value, target, minimum)

    status = metric(get_latest_metrics("quality-metrics-org"), key).status

    assert status.target_status == target_status
    assert status.minimum_status == minimum_status


def test_metric_without_standard_is_visible_and_not_invented():
    persist()
    item = metric(get_latest_metrics("quality-metrics-org"), "contact_compliance")

    assert item.current.numeric_value == 95.16
    assert item.standard.standard_available is False
    assert item.status.target_status == "NO_STANDARD"
    assert item.status.minimum_status == "NO_STANDARD"


@pytest.mark.parametrize("value_state", ["MISSING", "NOT_AVAILABLE", "NOT_APPLICABLE"])
def test_non_present_metric_is_not_evaluable(value_state):
    persist()
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_metric_observations "
            "SET value_state = ?, normalized_numeric_value = NULL, normalized_text_value = NULL "
            "WHERE metric_key = 'delivery_completion_rate'",
            (value_state,),
        )

    item = metric(get_latest_metrics("quality-metrics-org"), "delivery_completion_rate")

    assert item.current.value_state == value_state
    assert item.current.numeric_value is None
    assert item.status.target_status == "NOT_EVALUABLE"


def test_previous_scorecard_is_latest_available_even_with_week_gap():
    persist(week=43, metric_values={"photo_on_delivery": "94%"})
    persist(week=47, metric_values={"photo_on_delivery": "98%"})

    result = get_latest_metrics("quality-metrics-org")
    item = metric(result, "photo_on_delivery")

    assert result.previous_available is True
    assert (result.previous_period.week, result.previous_period.year) == (43, 2025)
    assert item.previous.numeric_value == 94.0


def test_previous_scorecard_never_crosses_station_or_dsp():
    persist(week=42, metric_values={"photo_on_delivery": "93%"})
    persist(week=45, station="DRO2", metric_values={"photo_on_delivery": "10%"})
    persist(week=46, dsp="OTHER", metric_values={"photo_on_delivery": "20%"})
    persist(week=47, metric_values={"photo_on_delivery": "98%"})

    result = get_latest_metrics("quality-metrics-org")

    assert result.previous_period.week == 42
    assert metric(result, "photo_on_delivery").previous.numeric_value == 93.0


def test_numeric_delta_is_current_minus_previous():
    persist(week=46, metric_values={"photo_on_delivery": "96%"})
    persist(week=47, metric_values={"photo_on_delivery": "98%"})

    delta = metric(get_latest_metrics("quality-metrics-org"), "photo_on_delivery").delta

    assert delta.numeric_delta == 2.0


def test_higher_is_better_positive_delta_is_improved():
    persist(week=46, metric_values={"photo_on_delivery": "96%"})
    persist(week=47, metric_values={"photo_on_delivery": "98%"})

    assert metric(
        get_latest_metrics("quality-metrics-org"), "photo_on_delivery"
    ).delta.direction_adjusted_improvement == "improved"


def test_lower_is_better_negative_delta_is_improved():
    persist(week=46, metric_values={"delivery_success_conditions_dpmo": "1000"})
    persist(week=47, metric_values={"delivery_success_conditions_dpmo": "700"})

    item = metric(get_latest_metrics("quality-metrics-org"), "delivery_success_conditions_dpmo")

    assert item.delta.numeric_delta == -300.0
    assert item.delta.direction_adjusted_improvement == "improved"


def test_unchanged_and_non_comparable_delta_are_explicit():
    persist(week=46, metric_values={"photo_on_delivery": "98%"})
    persist(week=47, metric_values={"photo_on_delivery": "98%"})

    item = metric(get_latest_metrics("quality-metrics-org"), "photo_on_delivery")

    assert item.delta.direction_adjusted_improvement == "unchanged"
    assert metric(
        get_latest_metrics("quality-metrics-org"), "breach_of_contract"
    ).delta.direction_adjusted_improvement == "unknown"


def test_amazon_rating_is_preserved_not_derived():
    persist()

    assert metric(
        get_latest_metrics("quality-metrics-org"), "delivery_completion_rate"
    ).current.rating == "Poor"


def test_metrics_are_strictly_organization_scoped():
    persist("quality-org-a", metric_values={"photo_on_delivery": "91%"})
    persist("quality-org-b", metric_values={"photo_on_delivery": "99%"})

    own = get_latest_metrics("quality-org-a")

    assert metric(own, "photo_on_delivery").current.numeric_value == 91.0


def test_active_revision_pointer_is_authoritative():
    first = persist(content=b"metrics-active-v1")
    persist(metric_values={"photo_on_delivery": "80%"}, content=b"metrics-active-v2")
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_scorecards SET active_revision_id = ? WHERE id = ?",
            (first.revision_id, first.scorecard_id),
        )

    item = metric(get_latest_metrics("quality-metrics-org"), "photo_on_delivery")

    assert item.current.numeric_value == 97.64


def test_summary_and_categories_are_derived_from_metric_read_model():
    persist()
    result = get_latest_metrics("quality-metrics-org")

    assert result.summary.evaluatable > 0
    assert result.summary.target_met + result.summary.attention <= result.summary.evaluatable
    assert result.categories == list(dict.fromkeys(item.category for item in result.metrics))
    assert "quality" in result.categories


def test_empty_organization_returns_semantic_empty():
    result = get_latest_metrics("quality-empty-org")

    assert result.available is False
    assert result.metrics == []
    assert result.previous_available is False


def test_metrics_endpoint_uses_authenticated_org_and_is_read_only():
    persist("test-organization")
    with db_session() as conn:
        before = conn.execute(
            "SELECT COUNT(*) count FROM dsp_quality_metric_observations"
        ).fetchone()["count"]

    response = TestClient(app).get("/api/dsp-quality/scorecards/latest/metrics")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["metrics"][0]["metric_key"]
    with db_session() as conn:
        after = conn.execute(
            "SELECT COUNT(*) count FROM dsp_quality_metric_observations"
        ).fetchone()["count"]
    assert after == before


def test_metrics_repository_is_batch_only_and_never_loads_transporter_rows():
    source = (
        Path(__file__).parents[1]
        / "app" / "plugins" / "dsp_quality" / "infrastructure" / "metrics_repository.py"
    ).read_text(encoding="utf-8")

    assert source.count("conn.execute(") == 3
    assert source.count("_metric_rows(") == 3  # helper definition + current/previous batches
    assert "dsp_quality_transporter_rows" not in source
    assert "dsp_quality_transporter_observations" not in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source

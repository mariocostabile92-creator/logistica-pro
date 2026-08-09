from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.drivers_read_service import get_latest_drivers
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.mapping_service import set_workforce_external_identity
from app.plugins.dsp_quality.domain.models import QualityMappingStatus


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
FIRST_TRANSPORTER = "A10GSCDE4XETEE"


def document(
    *,
    week: int = 47,
    year: int = 2025,
    transporter_count: int = 5,
    first_values: dict[str, str | None] | None = None,
) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    rows = []
    for index in range(transporter_count):
        template = base.transporter_rows[index % len(base.transporter_rows)]
        external_id = template.transporter_external_id if index < len(base.transporter_rows) else f"QA-{index + 1:04d}"
        metrics = template.metrics
        if index == 0 and first_values:
            metrics = [
                item.model_copy(update={"raw_value": first_values[item.metric_key]})
                if item.metric_key in first_values else item
                for item in metrics
            ]
        rows.append(template.model_copy(update={
            "row_index": index + 1,
            "transporter_external_id": external_id,
            "metrics": metrics,
        }))
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={
            "reported_week": week,
            "reported_year": year,
        }),
        "revision": base.revision.model_copy(update={
            "source_filename": f"Week-{week}-{year}.pdf",
            "raw_period_label": f"Week {week} - {year}",
        }),
        "transporter_rows": rows,
    })


def persist(
    organization_id: str = "quality-drivers-org",
    *,
    week: int = 47,
    year: int = 2025,
    transporter_count: int = 5,
    first_values: dict[str, str | None] | None = None,
    content: bytes | None = None,
):
    return ingest_quality_document(
        organization_id=organization_id,
        document=document(
            week=week,
            year=year,
            transporter_count=transporter_count,
            first_values=first_values,
        ),
        source_content=content or f"drivers-{organization_id}-{year}-{week}".encode(),
        imported_by="quality-drivers-test",
    )


def create_member(organization_id: str, display_name: str = "Alessandro Facchetti") -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'quality-drivers-test', ?, ?, ?)
            """,
            (
                f"WF-{organization_id}", display_name,
                "2026-08-09T10:00:00+00:00", "2026-08-09T10:00:00+00:00",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def map_transporter(
    organization_id: str,
    status: QualityMappingStatus,
    workforce_member_id: int | None = None,
    external_id: str = FIRST_TRANSPORTER,
):
    return set_workforce_external_identity(
        organization_id=organization_id,
        external_id=external_id,
        status=status,
        workforce_member_id=workforce_member_id,
        actor="quality-drivers-test",
    )


def row(result, external_id: str = FIRST_TRANSPORTER):
    return next(item for item in result.rows if item.transporter_external_id == external_id)


def metric(result_row, key: str):
    return next(item for item in result_row.metrics if item.metric_key == key)


def test_real_scale_read_model_returns_159_transporter_rows_and_eight_observations():
    persist(transporter_count=159)
    result = get_latest_drivers("quality-drivers-org")

    assert result.summary.total == 159
    assert len(result.rows) == 159
    assert all(len(item.metrics) == 8 for item in result.rows)


def test_transporter_observations_are_read_with_real_normalized_values():
    persist()
    first = row(get_latest_drivers("quality-drivers-org"))

    assert metric(first, "delivery_completion_rate").current.raw_value == "92.47%"
    assert metric(first, "customer_delivery_feedback_dpmo").current.numeric_value == 29630.0


def test_matched_mapping_returns_canonical_member_and_display_name():
    persist()
    member_id = create_member("quality-drivers-org")
    map_transporter("quality-drivers-org", QualityMappingStatus.MATCHED, member_id)

    first = row(get_latest_drivers("quality-drivers-org"))

    assert first.mapping_status == "MATCHED"
    assert first.workforce_member_id == member_id
    assert first.workforce_display_name == "Alessandro Facchetti"


def test_unmapped_transporter_is_explicit_and_does_not_expose_workforce():
    persist()
    first = row(get_latest_drivers("quality-drivers-org"))

    assert first.mapping_status == "UNMAPPED"
    assert first.workforce_member_id is None
    assert first.workforce_display_name is None


def test_ambiguous_mapping_never_selects_a_workforce_member():
    persist()
    map_transporter("quality-drivers-org", QualityMappingStatus.AMBIGUOUS)

    first = row(get_latest_drivers("quality-drivers-org"))

    assert first.mapping_status == "AMBIGUOUS"
    assert first.workforce_member_id is None


def test_mapping_is_exact_without_fuzzy_matching_or_member_auto_creation():
    persist()
    member_id = create_member("quality-drivers-org")
    map_transporter(
        "quality-drivers-org", QualityMappingStatus.MATCHED, member_id,
        external_id=FIRST_TRANSPORTER.lower(),
    )
    with db_session() as conn:
        before = conn.execute("SELECT COUNT(*) count FROM workforce_members").fetchone()["count"]

    first = row(get_latest_drivers("quality-drivers-org"))

    with db_session() as conn:
        after = conn.execute("SELECT COUNT(*) count FROM workforce_members").fetchone()["count"]
    assert first.mapping_status == "UNMAPPED"
    assert after == before


def test_previous_performance_matches_same_amazon_transporter_external_id():
    persist(week=46, first_values={"delivery_completion_rate": "95%"})
    persist(week=47, first_values={"delivery_completion_rate": "98%"})

    item = metric(row(get_latest_drivers("quality-drivers-org")), "delivery_completion_rate")

    assert item.previous.available is True
    assert item.previous.numeric_value == 95.0
    assert item.delta.numeric_delta == 3.0


def test_transporter_absent_from_previous_week_has_no_previous_value():
    persist(week=46, transporter_count=1)
    persist(week=47, transporter_count=5)

    item = metric(row(get_latest_drivers("quality-drivers-org"), "A13GR86JNE2BY9"), "photo_on_delivery")

    assert item.previous.available is False
    assert item.delta.direction_adjusted_improvement == "unknown"


def test_higher_is_better_positive_delta_is_improved():
    persist(week=46, first_values={"photo_on_delivery": "90%"})
    persist(week=47, first_values={"photo_on_delivery": "95%"})

    item = metric(row(get_latest_drivers("quality-drivers-org")), "photo_on_delivery")

    assert item.direction == "HIGHER_IS_BETTER"
    assert item.delta.direction_adjusted_improvement == "improved"


def test_lower_is_better_negative_delta_is_improved():
    persist(week=46, first_values={"delivery_success_conditions_dpmo": "500"})
    persist(week=47, first_values={"delivery_success_conditions_dpmo": "100"})

    item = metric(row(get_latest_drivers("quality-drivers-org")), "delivery_success_conditions_dpmo")

    assert item.direction == "LOWER_IS_BETTER"
    assert item.delta.direction_adjusted_improvement == "improved"


def test_delivered_is_volume_only_and_has_no_improvement_direction():
    persist(week=46, first_values={"delivered": "100"})
    persist(week=47, first_values={"delivered": "150"})

    item = metric(row(get_latest_drivers("quality-drivers-org")), "delivered")

    assert item.direction == "NO_DIRECTION"
    assert item.delta.numeric_delta == 50.0
    assert item.delta.direction_adjusted_improvement == "unknown"


@pytest.mark.parametrize("value_state", ["MISSING", "NOT_AVAILABLE", "NOT_APPLICABLE"])
def test_missing_and_unavailable_values_remain_semantic(value_state):
    raw = {"MISSING": None, "NOT_AVAILABLE": "n/a", "NOT_APPLICABLE": "not applicable"}[value_state]
    persist(first_values={"photo_on_delivery": raw})

    item = metric(row(get_latest_drivers("quality-drivers-org")), "photo_on_delivery")

    assert item.current.value_state == value_state
    assert item.current.numeric_value is None


def test_dsp_standard_is_never_misapplied_to_driver_metric():
    persist()

    first = row(get_latest_drivers("quality-drivers-org"))

    assert all(item.status == "NO_DRIVER_STANDARD" for item in first.metrics)


def test_active_revision_pointer_is_authoritative():
    first = persist(first_values={"photo_on_delivery": "91%"}, content=b"driver-active-v1")
    persist(first_values={"photo_on_delivery": "99%"}, content=b"driver-active-v2")
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_scorecards SET active_revision_id = ? WHERE id = ?",
            (first.revision_id, first.scorecard_id),
        )

    item = metric(row(get_latest_drivers("quality-drivers-org")), "photo_on_delivery")

    assert item.current.numeric_value == 91.0


def test_organization_isolation_covers_rows_mappings_and_workforce_names():
    persist("quality-org-a")
    persist("quality-org-b")
    member_b = create_member("quality-org-b", "Driver Segreto B")
    map_transporter("quality-org-b", QualityMappingStatus.MATCHED, member_b)

    own = row(get_latest_drivers("quality-org-a"))
    other = row(get_latest_drivers("quality-org-b"))

    assert own.mapping_status == "UNMAPPED"
    assert own.workforce_display_name is None
    assert other.workforce_display_name == "Driver Segreto B"


def test_empty_and_scorecard_without_transporter_rows_are_distinct():
    empty = get_latest_drivers("no-scorecard-org")
    persist("scorecard-no-rows", transporter_count=0)
    no_rows = get_latest_drivers("scorecard-no-rows")

    assert empty.available is False
    assert no_rows.available is True
    assert no_rows.drivers_available is False


def test_drivers_endpoint_uses_authenticated_organization_and_is_read_only():
    persist("test-organization")
    with db_session() as conn:
        before = conn.execute(
            "SELECT COUNT(*) count FROM dsp_quality_transporter_rows"
        ).fetchone()["count"]

    response = TestClient(app).get("/api/dsp-quality/scorecards/latest/drivers")

    assert response.status_code == 200
    assert response.json()["summary"]["total"] == 5
    with db_session() as conn:
        after = conn.execute(
            "SELECT COUNT(*) count FROM dsp_quality_transporter_rows"
        ).fetchone()["count"]
    assert after == before


def test_drivers_repository_is_batch_only_read_only_and_has_no_per_row_query():
    source = (
        Path(__file__).parents[1]
        / "app" / "plugins" / "dsp_quality" / "infrastructure" / "drivers_repository.py"
    ).read_text(encoding="utf-8")

    assert source.count("conn.execute(") == 3
    assert source.count("_transporter_rows(") == 3
    assert "workforce_external_identities" in source
    assert "workforce_members member" in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source

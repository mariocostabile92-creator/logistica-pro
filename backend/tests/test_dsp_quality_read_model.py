from pathlib import Path

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualityWorkingHourExceptionInput,
)
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.read_service import get_latest_scorecard


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"


def document(*, overall_score: str = "45.41", overall_standing: str = "Poor") -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    revision = base.revision.model_copy(update={
        "overall_score": overall_score,
        "overall_standing": overall_standing,
    })
    return base.model_copy(update={"revision": revision})


def persist(
    organization_id: str = "quality-read-org",
    *,
    content: bytes = b"quality-read-v1",
    source: QualityImportDocument | None = None,
):
    return ingest_quality_document(
        organization_id=organization_id,
        document=source or document(),
        source_content=content,
        imported_by="quality-reader-test",
    )


def test_latest_scorecard_available_with_persisted_identity():
    result = persist()

    latest = get_latest_scorecard("quality-read-org")

    assert latest.available is True
    assert latest.scorecard.id == result.scorecard_id
    assert latest.scorecard.revision_id == result.revision_id
    assert latest.scorecard.dsp_identifier == "PROF"
    assert latest.scorecard.station == "DLO2"
    assert (latest.scorecard.reported_week, latest.scorecard.reported_year) == (47, 2025)
    assert latest.scorecard.source_provider == "amazon"


def test_latest_uses_scorecard_active_revision_not_import_order():
    first = persist(content=b"active-pointer-v1")
    persist(
        content=b"active-pointer-v2",
        source=document(overall_score="88.20", overall_standing="Fantastic"),
    )
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_scorecards SET active_revision_id = ? WHERE id = ?",
            (first.revision_id, first.scorecard_id),
        )

    latest = get_latest_scorecard("quality-read-org")

    assert latest.scorecard.revision_id == first.revision_id
    assert str(latest.revision.overall_score) == "45.41"
    assert latest.revision.overall_standing == "Poor"


def test_superseded_revision_is_not_selected_after_normal_revision_change():
    first = persist(content=b"superseded-v1")
    second = persist(
        content=b"superseded-v2",
        source=document(overall_score="77.70", overall_standing="Great"),
    )

    latest = get_latest_scorecard("quality-read-org")

    assert latest.scorecard.revision_id == second.revision_id
    assert latest.scorecard.revision_id != first.revision_id
    assert str(latest.revision.overall_score) == "77.70"


def test_invalid_active_revision_uses_deterministic_fallback(caplog):
    persist(content=b"fallback-v1")
    second = persist(
        content=b"fallback-v2",
        source=document(overall_score="66.60", overall_standing="Fair"),
    )
    with db_session() as conn:
        conn.execute(
            "UPDATE dsp_quality_scorecards SET active_revision_id = 'missing-revision' "
            "WHERE organization_id = ?",
            ("quality-read-org",),
        )

    latest = get_latest_scorecard("quality-read-org")

    assert latest.scorecard.revision_id == second.revision_id
    assert str(latest.revision.overall_score) == "66.60"
    assert "active revision fallback" in caplog.text


def test_overall_score_standing_rank_and_wow_are_persisted():
    persist()

    revision = get_latest_scorecard("quality-read-org").revision

    assert str(revision.overall_score) == "45.41"
    assert revision.overall_standing == "Poor"
    assert revision.rank == 4
    assert revision.rank_wow_declared == -1


def test_section_standings_are_returned_from_active_revision():
    persist()

    sections = get_latest_scorecard("quality-read-org").sections

    assert {(item.section_key, item.label, item.standing) for item in sections} == {
        ("compliance_safety", "Compliance and Safety", "Fantastic"),
        ("delivery_quality_swc", "Delivery Quality & SWC", "Poor"),
        ("capacity", "Capacity", "Fantastic"),
    }


def test_focus_areas_are_ordered_by_source_position():
    persist()

    focus = get_latest_scorecard("quality-read-org").focus_areas

    assert [item.position for item in focus] == [1, 2, 3]
    assert [item.source_label for item in focus] == [
        "Delivery Success Conditions (DSC) DPMO",
        "Delivery Completion Rate (DCR)",
        "CDF DPMO",
    ]


def test_persisted_dsp_and_transporter_counts_are_aggregated():
    persist()

    counts = get_latest_scorecard("quality-read-org").counts

    assert counts.dsp_metrics == len(document().dsp_metrics)
    assert counts.transporter_rows == 5


def test_working_hour_exception_count_uses_persisted_rows():
    base = document()
    exception = QualityWorkingHourExceptionInput(
        transporter_external_id="A10GSCDE4XETEE",
        daily_limit_exceeded="Yes",
        wh_exception="Yes",
        source_page=9,
    )
    working_hours = base.working_hours.model_copy(update={"exceptions": [exception]})
    persist(source=base.model_copy(update={"working_hours": working_hours}))

    latest = get_latest_scorecard("quality-read-org")

    assert latest.counts.working_hour_exceptions == 1


def test_mapping_counts_are_aggregated_without_returning_rows():
    result = persist()
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id FROM dsp_quality_transporter_rows WHERE revision_id = ? ORDER BY row_index",
            (result.revision_id,),
        ).fetchall()
        conn.execute(
            "UPDATE dsp_quality_transporter_rows SET mapping_status = 'MATCHED' WHERE id = ?",
            (rows[0]["id"],),
        )
        conn.execute(
            "UPDATE dsp_quality_transporter_rows SET mapping_status = 'AMBIGUOUS' WHERE id = ?",
            (rows[1]["id"],),
        )

    counts = get_latest_scorecard("quality-read-org").counts

    assert counts.mapped_transporters == 1
    assert counts.ambiguous_transporters == 1
    assert counts.unmapped_transporters == 3


def test_source_and_standard_set_metadata_are_traceable():
    persist()

    latest = get_latest_scorecard("quality-read-org")

    assert latest.revision.source_filename == "IT-PROF-DLO2-Week47-DSP-Scorecard-3.0.pdf"
    assert latest.revision.detected_template_version == "3.0"
    assert latest.revision.imported_at is not None
    assert latest.revision.imported_by == "quality-reader-test"
    assert latest.standard_set.available is True
    assert latest.standard_set.provider == "amazon"
    assert latest.standard_set.version == "3.0"


def test_no_scorecard_returns_semantic_empty_response():
    latest = get_latest_scorecard("quality-empty-org")

    assert latest.available is False
    assert latest.scorecard is None
    assert latest.revision is None
    assert latest.sections == []
    assert latest.focus_areas == []


def test_latest_is_strictly_isolated_by_organization():
    persist("quality-org-a", content=b"org-a", source=document(overall_score="10.10"))
    persist("quality-org-b", content=b"org-b", source=document(overall_score="90.90"))

    own = get_latest_scorecard("quality-org-a")

    assert str(own.revision.overall_score) == "10.10"
    assert own.counts.transporter_rows == 5
    assert own.scorecard.id != get_latest_scorecard("quality-org-b").scorecard.id


def test_latest_endpoint_uses_authenticated_organization_and_read_permission():
    persist("test-organization", content=b"endpoint-latest")
    client = TestClient(app)

    response = client.get("/api/dsp-quality/scorecards/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["scorecard"]["dsp_identifier"] == "PROF"
    assert payload["revision"]["overall_score"] == "45.41"


def test_latest_endpoint_empty_is_200_not_server_error():
    response = TestClient(app).get("/api/dsp-quality/scorecards/latest")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_read_model_does_not_modify_persisted_quality_tables():
    persist()
    tables = [
        "dsp_quality_scorecards",
        "dsp_quality_scorecard_versions",
        "dsp_quality_metric_observations",
        "dsp_quality_transporter_rows",
        "dsp_quality_section_standings",
        "dsp_quality_focus_areas",
    ]
    with db_session() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) count FROM {table}").fetchone()["count"]
            for table in tables
        }

    get_latest_scorecard("quality-read-org")

    with db_session() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) count FROM {table}").fetchone()["count"]
            for table in tables
        }
    assert after == before


def test_read_repository_uses_fixed_batch_queries_without_n_plus_one():
    repository_source = (
        Path(__file__).parents[1]
        / "app" / "plugins" / "dsp_quality" / "infrastructure" / "read_repository.py"
    ).read_text(encoding="utf-8")

    assert repository_source.count("conn.execute(") == 4
    assert "for item in" not in repository_source
    assert "INSERT " not in repository_source
    assert "UPDATE " not in repository_source
    assert "DELETE " not in repository_source

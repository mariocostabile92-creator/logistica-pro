import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.database import db_session
from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualitySourceInput,
)
from app.plugins.dsp_quality.application.import_service import (
    ingest_quality_document,
    ingest_quality_source,
)
from app.plugins.dsp_quality.application.mapping_service import (
    resolve_workforce_external_identity,
    set_workforce_external_identity,
)
from app.plugins.dsp_quality.application.normalization import normalize_quality_value
from app.plugins.dsp_quality.domain.models import (
    QualityMappingStatus,
    QualityValueState,
    QualityValueType,
)
from app.plugins.dsp_quality.infrastructure import repository
from app.plugins.dsp_quality.infrastructure.schema import init_schema


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"


def fixture_document() -> QualityImportDocument:
    return QualityImportDocument.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )


def import_fixture(
    organization_id: str = "quality-org-a",
    content: bytes = b"amazon-week47-scorecard-v1",
):
    return ingest_quality_document(
        organization_id=organization_id,
        document=fixture_document(),
        source_content=content,
        imported_by="quality-admin",
    )


def create_member(organization_id: str, external_identifier: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'quality-test', ?, ?, ?)
            """,
            (
                external_identifier,
                f"Driver {external_identifier}",
                "2026-08-09T10:00:00+00:00",
                "2026-08-09T10:00:00+00:00",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def test_real_week47_fixture_preserves_confirmed_source_values():
    document = fixture_document()

    assert document.identity.model_dump() == {
        "source_provider": "amazon",
        "dsp_identifier": "PROF",
        "station": "DLO2",
        "reported_year": 2025,
        "reported_week": 47,
        "geography": "IT",
    }
    assert document.revision.rank == 4
    assert document.revision.rank_wow_declared == -1
    assert document.revision.overall_score == "45.41"
    assert document.revision.overall_standing == "Poor"
    assert len(document.transporter_rows) == 5
    assert document.transporter_rows[0].transporter_external_id == "A10GSCDE4XETEE"
    assert document.transporter_rows[0].metrics[0].raw_value == "135"
    assert document.working_hours.section_present is True
    assert document.working_hours.exceptions == []
    assert [item.source_label for item in document.focus_areas] == [
        "Delivery Success Conditions (DSC) DPMO",
        "Delivery Completion Rate (DCR)",
        "CDF DPMO",
    ]


@pytest.mark.parametrize(
    ("raw", "value_type", "state", "numeric", "text"),
    [
        ("97.64%", QualityValueType.PERCENTAGE, QualityValueState.PRESENT, Decimal("97.64"), None),
        ("1355", QualityValueType.DPMO, QualityValueState.PRESENT, Decimal("1355"), None),
        ("0", QualityValueType.COUNT, QualityValueState.PRESENT, Decimal("0"), None),
        ("45.41", QualityValueType.SCORE, QualityValueState.PRESENT, Decimal("45.41"), None),
        ("None", QualityValueType.COMPLIANCE_STATE, QualityValueState.PRESENT, None, "None"),
        ("-", QualityValueType.PERCENTAGE, QualityValueState.NOT_AVAILABLE, None, None),
        ("", QualityValueType.PERCENTAGE, QualityValueState.MISSING, None, None),
        ("N/A", QualityValueType.SCORE, QualityValueState.NOT_AVAILABLE, None, None),
        ("not applicable", QualityValueType.SCORE, QualityValueState.NOT_APPLICABLE, None, None),
    ],
)
def test_value_normalization_preserves_semantics(raw, value_type, state, numeric, text):
    value = normalize_quality_value(
        raw,
        value_type,
        rule_version="amazon_scorecard_3.0",
    )

    assert value.raw_value == raw
    assert value.value_state is state
    assert value.normalized_numeric_value == numeric
    assert value.normalized_text_value == text


def test_value_and_rating_are_separate_fields():
    value = normalize_quality_value(
        "97.64%",
        QualityValueType.PERCENTAGE,
        rating="Fantastic",
        rule_version="amazon_scorecard_3.0",
    )

    assert value.raw_value == "97.64%"
    assert value.normalized_numeric_value == Decimal("97.64")
    assert value.rating == "Fantastic"
    assert "|" not in value.raw_value


def test_first_import_creates_scorecard_revision_and_real_observations():
    result = import_fixture()

    assert result.revision_created is True
    assert result.idempotent is False
    assert result.active_revision_id == result.revision_id
    assert result.transporter_rows == 5
    scorecards = repository.list_scorecards("quality-org-a")
    revisions = repository.list_revisions("quality-org-a", result.scorecard_id)
    observations = repository.list_metric_observations(result.revision_id)
    assert len(scorecards) == 1
    assert len(revisions) == 1
    assert revisions[0]["status"] == "active"
    assert revisions[0]["working_hours_section_present"] == 1
    assert revisions[0]["working_hours_exception_count"] == 0
    assert len(observations) == len(fixture_document().dsp_metrics)
    pod = next(item for item in observations if item["metric_key"] == "photo_on_delivery")
    assert pod["raw_value"] == "97.64%"
    assert pod["normalized_numeric_value"] == "97.64"
    assert pod["rating"] == "Fantastic"


def test_same_fingerprint_is_idempotent_noop():
    first = import_fixture()
    second = import_fixture()

    assert second.idempotent is True
    assert second.revision_created is False
    assert second.scorecard_id == first.scorecard_id
    assert second.revision_id == first.revision_id
    assert len(repository.list_revisions("quality-org-a", first.scorecard_id)) == 1


def test_changed_fingerprint_creates_revision_and_preserves_previous():
    first = import_fixture(content=b"week47-original")
    second = import_fixture(content=b"week47-corrected")

    assert second.scorecard_id == first.scorecard_id
    assert second.revision_id != first.revision_id
    assert second.previous_revision_id == first.revision_id
    revisions = repository.list_revisions("quality-org-a", first.scorecard_id)
    assert len(revisions) == 2
    by_id = {item["id"]: item for item in revisions}
    assert by_id[first.revision_id]["status"] == "superseded"
    assert by_id[first.revision_id]["active"] == 0
    assert by_id[second.revision_id]["status"] == "active"
    assert by_id[second.revision_id]["active"] == 1
    assert repository.list_scorecards("quality-org-a")[0]["active_revision_id"] == second.revision_id


def test_identical_week_and_fingerprint_are_isolated_by_organization():
    first = import_fixture("quality-org-a", b"shared-scorecard-source")
    second = import_fixture("quality-org-b", b"shared-scorecard-source")

    assert first.scorecard_id != second.scorecard_id
    assert first.revision_id != second.revision_id
    assert len(repository.list_scorecards("quality-org-a")) == 1
    assert len(repository.list_scorecards("quality-org-b")) == 1


def test_metric_definition_seed_is_idempotent():
    before = repository.metric_definition_count()
    init_schema()
    init_schema()

    assert before == 22
    assert repository.metric_definition_count() == before


def test_transporter_is_unmapped_without_external_identity_and_creates_no_member():
    with db_session() as conn:
        before = conn.execute("SELECT COUNT(*) count FROM workforce_members").fetchone()["count"]
    result = import_fixture(content=b"unmapped-source")
    rows = repository.list_transporter_rows(result.revision_id)
    with db_session() as conn:
        after = conn.execute("SELECT COUNT(*) count FROM workforce_members").fetchone()["count"]

    assert {item["mapping_status"] for item in rows} == {"UNMAPPED"}
    assert all(item["workforce_member_id"] is None for item in rows)
    assert before == after


def test_exact_amazon_mapping_is_organization_scoped_and_audited():
    member_id = create_member("quality-org-a", "driver-internal-1")
    mapping = set_workforce_external_identity(
        organization_id="quality-org-a",
        external_id="A10GSCDE4XETEE",
        status=QualityMappingStatus.MATCHED,
        workforce_member_id=member_id,
        actor="quality-admin",
    )
    result = import_fixture(content=b"mapped-source")
    first_row = repository.list_transporter_rows(result.revision_id)[0]
    with db_session() as conn:
        events = conn.execute(
            "SELECT COUNT(*) count FROM workforce_external_identity_events WHERE identity_id = ?",
            (mapping.id,),
        ).fetchone()["count"]

    assert mapping.source == "amazon_transporter"
    assert first_row["mapping_status"] == "MATCHED"
    assert first_row["workforce_member_id"] == member_id
    assert events == 1
    assert resolve_workforce_external_identity(
        organization_id="quality-org-b",
        external_id="A10GSCDE4XETEE",
    ) is None


def test_cross_organization_mapping_is_rejected_and_no_fuzzy_match_occurs():
    member_id = create_member("quality-org-b", "driver-b")
    with pytest.raises(ValueError, match="not found in organization"):
        set_workforce_external_identity(
            organization_id="quality-org-a",
            external_id="A10GSCDE4XETEE",
            status=QualityMappingStatus.MATCHED,
            workforce_member_id=member_id,
            actor="quality-admin",
        )
    set_workforce_external_identity(
        organization_id="quality-org-b",
        external_id="A10GSCDE4XETEE",
        status=QualityMappingStatus.MATCHED,
        workforce_member_id=member_id,
        actor="quality-admin",
    )

    assert resolve_workforce_external_identity(
        organization_id="quality-org-b",
        external_id="A10GSCDE4XETE",
    ) is None


def test_standard_rules_are_immutable_revision_data_from_fixture():
    result = import_fixture(content=b"standard-source")
    revisions = repository.list_revisions("quality-org-a", result.scorecard_id)
    standard_set_id = revisions[0]["standard_set_id"]
    with db_session() as conn:
        rules = conn.execute(
            "SELECT * FROM dsp_quality_standard_rules WHERE standard_set_id = ? ORDER BY metric_key",
            (standard_set_id,),
        ).fetchall()

    assert len(rules) == 6
    dcr = next(row for row in rules if row["metric_key"] == "delivery_completion_rate")
    assert dcr["target_value"] == "97.9"
    assert dcr["minimum_value"] == "97"
    assert dcr["raw_target"] == "97.9%"


class FixtureAdapter:
    adapter_id = "fixture.amazon_scorecard"
    parser_version = "q2-fixture-1"

    def __init__(self, document):
        self.document = document

    def supports(self, source):
        return source.filename.casefold().endswith(".pdf")

    def detect_template(self, source):
        return "3.0"

    def extract_identity(self, source):
        return self.document.identity

    def extract_revision(self, source):
        return self.document.revision.model_copy(update={"detected_template_version": None})

    def extract_dsp_metrics(self, source):
        return self.document.dsp_metrics

    def extract_section_standings(self, source):
        return self.document.sections

    def extract_transporter_rows(self, source):
        return self.document.transporter_rows

    def extract_working_hour_exceptions(self, source):
        return self.document.working_hours

    def extract_focus_areas(self, source):
        return self.document.focus_areas

    def extract_standard_rules(self, source):
        return self.document.standards


def test_adapter_pipeline_selects_source_and_persists_format_independent_dto():
    document = fixture_document()
    source = QualitySourceInput(
        filename=document.revision.source_filename,
        content=b"pdf-fixture-contract",
        media_type="application/pdf",
    )

    result = ingest_quality_source(
        organization_id="quality-org-a",
        source=source,
        adapters=[FixtureAdapter(document)],
        imported_by="quality-admin",
    )

    revision = repository.list_revisions("quality-org-a", result.scorecard_id)[0]
    assert result.revision_created is True
    assert revision["detected_template_version"] == "3.0"
    assert revision["parser_adapter"] == "fixture.amazon_scorecard"


def test_schema_contract_avoids_sqlite_only_migration_constructs():
    source = (
        Path(__file__).parents[1]
        / "app" / "plugins" / "dsp_quality" / "infrastructure" / "schema.py"
    ).read_text(encoding="utf-8")

    assert "AUTOINCREMENT" not in source
    assert "PRAGMA" not in source
    assert "INSERT OR IGNORE" not in source

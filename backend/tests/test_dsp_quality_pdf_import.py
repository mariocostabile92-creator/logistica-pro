from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.attachments import repository as attachment_repository
from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualitySourceInput,
)
from app.plugins.dsp_quality.application.mapping_service import (
    set_workforce_external_identity,
)
from app.plugins.dsp_quality.application.preview_models import (
    QualityImportAction,
)
from app.plugins.dsp_quality.application.preview_service import (
    QualityPreviewError,
    confirm_scorecard_import,
    preview_scorecard_import,
)
from app.plugins.dsp_quality.domain.models import QualityMappingStatus
from app.plugins.dsp_quality.infrastructure import repository
from app.plugins.dsp_quality.infrastructure.adapters import AmazonScorecardPdfAdapter


REAL_PDF_PATH = (
    Path.home() / "Downloads" / "IT-PROF-DLO2-Week47-DSP-Scorecard-3.0.pdf"
)
FOUNDATION_FIXTURE = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"


def real_source(content: bytes | None = None) -> QualitySourceInput:
    if not REAL_PDF_PATH.is_file():
        pytest.skip(f"Real Amazon scorecard fixture not available: {REAL_PDF_PATH}")
    return QualitySourceInput(
        filename=REAL_PDF_PATH.name,
        content=REAL_PDF_PATH.read_bytes() if content is None else content,
        media_type="application/pdf",
    )


def foundation_document() -> QualityImportDocument:
    return QualityImportDocument.model_validate_json(
        FOUNDATION_FIXTURE.read_text(encoding="utf-8")
    )


def table_count(table: str) -> int:
    with db_session() as conn:
        return int(conn.execute(f"SELECT COUNT(*) count FROM {table}").fetchone()["count"])


def create_member(organization_id: str, external_identifier: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'quality-pdf-test', ?, ?, ?)
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


class DocumentAdapter:
    adapter_id = "test.scorecard.pdf"
    parser_version = "test.1"

    def __init__(self, document: QualityImportDocument):
        self.document = document

    def supports(self, source):
        return True

    def detect_template(self, source):
        return "amazon_scorecard_pdf_3_x"

    def geography_is_inferred(self, source):
        return False

    def extract_identity(self, source):
        return self.document.identity

    def extract_revision(self, source):
        return self.document.revision

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


def test_real_pdf_adapter_extracts_confirmed_identity_metrics_and_sections():
    source = real_source()
    adapter = AmazonScorecardPdfAdapter()

    assert adapter.supports(source) is True
    assert adapter.detect_template(source) == "amazon_scorecard_pdf_3_x"
    identity = adapter.extract_identity(source)
    revision = adapter.extract_revision(source)
    metrics = {item.metric_key: item for item in adapter.extract_dsp_metrics(source)}
    sections = {item.section_key: item.standing for item in adapter.extract_section_standings(source)}

    assert identity.model_dump() == {
        "source_provider": "amazon",
        "dsp_identifier": "PROF",
        "station": "DLO2",
        "reported_year": 2025,
        "reported_week": 47,
        "geography": "IT",
    }
    assert revision.rank == 4
    assert revision.rank_wow_declared == -1
    assert revision.overall_score == "45.41"
    assert revision.overall_standing == "Poor"
    assert len(metrics) == 18
    assert metrics["photo_on_delivery"].raw_value == "97.64%"
    assert metrics["photo_on_delivery"].rating == "Fantastic"
    assert metrics["safe_driving_fico"].raw_value == "N/A"
    assert sections == {
        "compliance_and_safety": "Fantastic",
        "delivery_quality_and_swc": "Poor",
        "capacity": "Fantastic",
    }


def test_real_pdf_adapter_extracts_all_transporter_rows_and_observations():
    rows = AmazonScorecardPdfAdapter().extract_transporter_rows(real_source())

    assert len(rows) == 159
    assert rows[0].transporter_external_id == "A10GSCDE4XETEE"
    assert rows[-1].transporter_external_id == "AZRHNPVVB8QRZ"
    assert rows[0].source_page == 3
    assert rows[-1].source_page == 5
    assert len(rows[0].metrics) == 8
    first = {item.metric_key: item.raw_value for item in rows[0].metrics}
    assert first == {
        "delivered": "135",
        "delivery_completion_rate": "92.47%",
        "delivery_success_conditions_dpmo": "0",
        "lost_on_road_dpmo": "0",
        "photo_on_delivery": "96.88%",
        "contact_compliance": "88%",
        "customer_escalations_count": "0",
        "customer_delivery_feedback_dpmo": "29630",
    }


def test_real_pdf_working_hours_focus_and_standards_are_not_invented():
    adapter = AmazonScorecardPdfAdapter()
    source = real_source()
    working_hours = adapter.extract_working_hour_exceptions(source)
    focus = adapter.extract_focus_areas(source)
    standards = adapter.extract_standard_rules(source)

    assert working_hours.section_present is True
    assert working_hours.exceptions == []
    assert [item.source_label for item in focus] == [
        "Delivery Success Conditions (DSC) DPMO",
        "Delivery Completion Rate (DCR)",
        "CDF DPMO",
    ]
    assert standards is not None
    assert len(standards.rules) == 13
    assert {item.source_page for item in standards.rules} == {7}
    dcr = next(item for item in standards.rules if item.metric_key == "delivery_completion_rate")
    assert dcr.raw_target == "97.9%"
    assert dcr.raw_minimum == "97%"


def test_preview_normalizes_real_pdf_and_writes_nothing():
    before = table_count("dsp_quality_scorecards")
    preview = preview_scorecard_import(
        organization_id="quality-preview-org",
        source=real_source(),
    )

    assert preview.valid is True
    assert preview.preview_token
    assert preview.identity.dsp_identifier == "PROF"
    assert preview.identity.geography == "IT"
    assert preview.identity.geography_authoritative is False
    assert preview.counts.model_dump() == {
        "dsp_metrics_count": 18,
        "transporter_rows_count": 159,
        "working_hours_exception_count": 0,
        "focus_areas_count": 3,
        "standards_count": 13,
    }
    assert preview.working_hours_section_present is True
    assert preview.idempotency.action is QualityImportAction.CREATE
    assert preview.mapping.unmapped_transporters == 159
    pod = next(item for item in preview.dsp_metrics if item.metric_key == "photo_on_delivery")
    assert str(pod.normalized_numeric_value) == "97.64"
    assert pod.raw_value == "97.64%"
    assert pod.rating == "Fantastic"
    assert not preview.validation.errors
    assert {item.code for item in preview.validation.warnings} >= {
        "GEOGRAPHY_INFERRED",
        "AMBIGUOUS_NA_VALUES",
        "UNMAPPED_TRANSPORTERS",
    }
    assert table_count("dsp_quality_scorecards") == before
    assert table_count("dsp_quality_scorecard_versions") == 0


def test_preview_rejects_duplicate_transporter_and_missing_identity():
    document = foundation_document()
    duplicate = document.transporter_rows[0].model_copy(update={"row_index": 99})
    duplicate_document = document.model_copy(
        update={"transporter_rows": [*document.transporter_rows, duplicate]}
    )
    duplicate_preview = preview_scorecard_import(
        organization_id="quality-org",
        source=real_source(),
        adapters=[DocumentAdapter(duplicate_document)],
    )
    missing_identity = document.model_copy(
        update={"identity": document.identity.model_copy(update={"dsp_identifier": ""})}
    )
    missing_preview = preview_scorecard_import(
        organization_id="quality-org",
        source=real_source(),
        adapters=[DocumentAdapter(missing_identity)],
    )

    assert duplicate_preview.valid is False
    assert "DUPLICATE_TRANSPORTER_IDS" in {
        item.code for item in duplicate_preview.validation.errors
    }
    assert missing_preview.valid is False
    assert "MISSING_DSP_IDENTIFIER" in {
        item.code for item in missing_preview.validation.errors
    }


def test_mapping_preview_is_exact_nonblocking_and_organization_scoped():
    member_id = create_member("quality-org-a", "member-a")
    set_workforce_external_identity(
        organization_id="quality-org-a",
        external_id="A10GSCDE4XETEE",
        status=QualityMappingStatus.MATCHED,
        workforce_member_id=member_id,
        actor="quality-admin",
    )

    own = preview_scorecard_import(organization_id="quality-org-a", source=real_source())
    other = preview_scorecard_import(organization_id="quality-org-b", source=real_source())

    assert own.valid is True
    assert own.mapping.matched_transporters == 1
    assert own.mapping.unmapped_transporters == 158
    assert other.mapping.matched_transporters == 0
    assert other.mapping.unmapped_transporters == 159
    assert table_count("workforce_members") == 1


def test_confirm_create_noop_and_new_revision_preserve_source_and_history():
    source = real_source()
    first_preview = preview_scorecard_import(
        organization_id="quality-import-org",
        source=source,
    )
    first = confirm_scorecard_import(
        organization_id="quality-import-org",
        source=source,
        preview_token=first_preview.preview_token,
        imported_by="quality-admin",
        expected_action=QualityImportAction.CREATE,
    )
    noop_preview = preview_scorecard_import(
        organization_id="quality-import-org",
        source=source,
    )
    noop = confirm_scorecard_import(
        organization_id="quality-import-org",
        source=source,
        preview_token=noop_preview.preview_token,
        imported_by="quality-admin",
        expected_action=QualityImportAction.NO_OP,
    )
    changed_source = real_source(source.content + b"\nQ3 corrected source revision")
    revision_preview = preview_scorecard_import(
        organization_id="quality-import-org",
        source=changed_source,
    )
    second = confirm_scorecard_import(
        organization_id="quality-import-org",
        source=changed_source,
        preview_token=revision_preview.preview_token,
        imported_by="quality-admin",
        expected_action=QualityImportAction.NEW_REVISION,
    )

    assert first.action is QualityImportAction.CREATE
    assert first.source_attachment_reference
    assert noop.action is QualityImportAction.NO_OP
    assert noop.revision_id == first.revision_id
    assert noop.source_attachment_reference == first.source_attachment_reference
    assert second.action is QualityImportAction.NEW_REVISION
    assert second.previous_revision_id == first.revision_id
    assert second.revision_id != first.revision_id
    revisions = repository.list_revisions("quality-import-org", first.scorecard_id)
    assert len(revisions) == 2
    assert {item["status"] for item in revisions} == {"active", "superseded"}
    assert len(attachment_repository.list_for_entity(
        "quality_scorecard",
        repository.scorecard_attachment_entity_id("quality-import-org", first.scorecard_id),
        "quality-import-org",
    )) == 2
    observations = repository.list_metric_observations(second.revision_id)
    assert next(item for item in observations if item["metric_key"] == "photo_on_delivery")["raw_value"] == "97.64%"
    rows = repository.list_transporter_rows(second.revision_id)
    assert rows[0]["raw_row_fingerprint"]
    with db_session() as conn:
        standard_pages = conn.execute(
            """
            SELECT DISTINCT r.source_page
            FROM dsp_quality_standard_rules r
            JOIN dsp_quality_scorecard_versions v ON v.standard_set_id = r.standard_set_id
            WHERE v.id = ?
            """,
            (second.revision_id,),
        ).fetchall()
        workforce_count = conn.execute(
            "SELECT COUNT(*) count FROM workforce_members"
        ).fetchone()["count"]
    assert [row["source_page"] for row in standard_pages] == [7]
    assert workforce_count == 0


def test_confirm_rejects_tampered_stale_and_cross_org_preview_tokens():
    source = real_source()
    preview = preview_scorecard_import(organization_id="quality-org-a", source=source)

    with pytest.raises(QualityPreviewError, match="token non valido"):
        confirm_scorecard_import(
            organization_id="quality-org-a",
            source=source,
            preview_token=preview.preview_token[:-1] + "x",
            imported_by="quality-admin",
        )
    with pytest.raises(QualityPreviewError, match="non coerente"):
        confirm_scorecard_import(
            organization_id="quality-org-b",
            source=source,
            preview_token=preview.preview_token,
            imported_by="quality-admin",
        )

    confirm_scorecard_import(
        organization_id="quality-org-a",
        source=source,
        preview_token=preview.preview_token,
        imported_by="quality-admin",
    )
    with pytest.raises(QualityPreviewError, match="non piu attuale"):
        confirm_scorecard_import(
            organization_id="quality-org-a",
            source=source,
            preview_token=preview.preview_token,
            imported_by="quality-admin",
        )


def test_new_week_preview_is_create_without_persisting():
    document = foundation_document()
    source = real_source()
    first = preview_scorecard_import(
        organization_id="quality-org",
        source=source,
        adapters=[DocumentAdapter(document)],
    )
    confirm_scorecard_import(
        organization_id="quality-org",
        source=source,
        preview_token=first.preview_token,
        imported_by="quality-admin",
        adapters=[DocumentAdapter(document)],
    )
    next_week = document.model_copy(
        update={"identity": document.identity.model_copy(update={"reported_week": 48})}
    )
    preview = preview_scorecard_import(
        organization_id="quality-org",
        source=real_source(source.content + b"\nweek48"),
        adapters=[DocumentAdapter(next_week)],
    )

    assert preview.idempotency.action is QualityImportAction.CREATE
    assert len(repository.list_scorecards("quality-org")) == 1


def test_unrecognized_pdf_template_is_a_blocking_preview_error():
    preview = preview_scorecard_import(
        organization_id="quality-org",
        source=QualitySourceInput(
            filename="unknown.pdf",
            content=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
            media_type="application/pdf",
        ),
    )

    assert preview.valid is False
    assert preview.preview_token is None
    assert [item.code for item in preview.validation.errors] == [
        "TEMPLATE_NOT_RECOGNIZED"
    ]


def test_api_preview_import_permissions_security_and_attachment_link():
    if not REAL_PDF_PATH.is_file():
        pytest.skip("Real Amazon scorecard fixture not available")
    client = TestClient(app)
    pdf = REAL_PDF_PATH.read_bytes()
    response = client.post(
        "/api/dsp-quality/scorecards/preview",
        files={"file": (REAL_PDF_PATH.name, pdf, "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["idempotency"]["action"] == "CREATE"
    imported = client.post(
        "/api/dsp-quality/scorecards/import",
        data={
            "preview_token": payload["preview_token"],
            "expected_action": "CREATE",
        },
        files={"file": (REAL_PDF_PATH.name, pdf, "application/pdf")},
    )
    assert imported.status_code == 200
    assert imported.json()["source_attachment_reference"]

    wrong_type = client.post(
        "/api/dsp-quality/scorecards/preview",
        files={"file": ("scorecard.txt", b"not a pdf", "text/plain")},
    )
    assert wrong_type.status_code == 415

    viewer = TestClient(app, headers={"X-Auth-Enforce": "1"})
    password = "Password-sicura-123"
    create_user(
        "quality-viewer@example.test",
        hash_password(password),
        Role.VIEWER,
        "Quality Viewer Org",
    )
    assert viewer.post(
        "/api/auth/login",
        json={"email": "quality-viewer@example.test", "password": password},
    ).status_code == 200
    denied = viewer.post(
        "/api/dsp-quality/scorecards/preview",
        files={"file": (REAL_PDF_PATH.name, pdf, "application/pdf")},
    )
    assert denied.status_code == 403


def test_q3_sql_uses_database_abstraction_and_portable_schema_migrations():
    quality_root = (
        Path(__file__).parents[1] / "app" / "plugins" / "dsp_quality"
    )
    schema = (quality_root / "infrastructure" / "schema.py").read_text(
        encoding="utf-8"
    )
    repository_source = (
        quality_root / "infrastructure" / "repository.py"
    ).read_text(encoding="utf-8")

    assert "AUTOINCREMENT" not in schema
    assert "INSERT OR" not in schema
    assert "ensure_column" in schema
    assert "db_session" in repository_source
    assert "%s" not in repository_source

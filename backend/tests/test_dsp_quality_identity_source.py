import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.identity_source_service import (
    IdentitySourceError,
    apply_exact_identity_matches,
    preview_identity_source,
)
from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualitySourceInput,
)
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.reconciliation_service import put_mapping, reconciliation_state
from app.plugins.dsp_quality.infrastructure.adapters.tabular_identity_source import IdentitySourceSelection


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
FIRST = "A10GSCDE4XETEE"
SECOND = "A1220Y3BKPI76Z"


def _document(week: int = 45) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={"reported_week": week}),
        "revision": base.revision.model_copy(update={"source_filename": f"Week-{week}.pdf"}),
    })


def _persist(organization_id: str, week: int = 45):
    return ingest_quality_document(
        organization_id=organization_id,
        document=_document(week),
        source_content=f"quality-{organization_id}-{week}".encode(),
        imported_by="q82-test",
    )


def _member(organization_id: str, name: str, external_identifier: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO workforce_members (
                external_identifier, display_name, station, employment_type,
                capabilities, active, source_reference, created_at, updated_at,
                organization_id
            ) VALUES (?, ?, 'DLO2', 'full_time', '[]', 1, 'q82', ?, ?, ?)""",
            (external_identifier, name, "2026-08-09T10:00:00+00:00", "2026-08-09T10:00:00+00:00", organization_id),
        )
        return int(cursor.lastrowid)


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _source(rows: list[list[object]], *, header: list[str] | None = None, filename: str = "source.xlsx"):
    content = _xlsx({"Planning": [header or ["T-ID", "drivers"], *rows]})
    return QualitySourceInput(filename=filename, content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _preview(org: str, scorecard_id: str, source: QualitySourceInput):
    return preview_identity_source(organization_id=org, scorecard_id=scorecard_id, source=source)


def test_generic_xlsx_detects_tid_driver_sheet_and_rows():
    scorecard = _persist("q82-xlsx")
    preview = _preview("q82-xlsx", scorecard.scorecard_id, _source([[FIRST, "Mario Rossi"]]))
    assert preview.schema_status == "READY"
    assert preview.source.sheet == "Planning"
    assert preview.source.transporter_column == "T-ID"
    assert preview.source.driver_column == "drivers"
    assert preview.source.rows_detected == 1


def test_csv_detection_uses_semantic_headers_not_positions():
    scorecard = _persist("q82-csv")
    source = QualitySourceInput(
        filename="source.csv",
        content=f"ignore,Driver Name,Transporter ID\nx,Mario Rossi,{FIRST}\n".encode(),
        media_type="text/csv",
    )
    preview = _preview("q82-csv", scorecard.scorecard_id, source)
    assert preview.source.sheet == "CSV"
    assert preview.source.transporter_column == "Transporter ID"
    assert preview.source.driver_column == "Driver Name"


def test_multi_sheet_valid_schema_requires_explicit_selection():
    scorecard = _persist("q82-multi")
    source = QualitySourceInput(filename="multi.xlsx", content=_xlsx({
        "One": [["T-ID", "drivers"], [FIRST, "Mario"]],
        "Two": [["Transporter ID", "Driver"], [FIRST, "Mario"]],
    }))
    preview = _preview("q82-multi", scorecard.scorecard_id, source)
    assert preview.schema_status == "AMBIGUOUS_SCHEMA"
    assert preview.source.candidate_sheets == ["One", "Two"]
    selected = preview_identity_source(
        organization_id="q82-multi", scorecard_id=scorecard.scorecard_id, source=source,
        selection=IdentitySourceSelection(sheet="Two"),
    )
    assert selected.source.sheet == "Two"


def test_ambiguous_columns_are_never_selected_arbitrarily():
    scorecard = _persist("q82-columns")
    source = _source([[FIRST, FIRST, "Mario"]], header=["T-ID", "Transporter ID", "drivers"])
    preview = _preview("q82-columns", scorecard.scorecard_id, source)
    assert preview.schema_status == "AMBIGUOUS_SCHEMA"
    assert set(preview.source.transporter_candidates) == {"T-ID", "Transporter ID"}


def test_coverage_uses_selected_scorecard_only():
    old = _persist("q82-selected", 45)
    _persist("q82-selected", 47)
    preview = _preview("q82-selected", old.scorecard_id, _source([[FIRST, "Mario"]]))
    assert preview.scorecard_id == old.scorecard_id
    assert preview.coverage.quality_transporters == 5


def test_verified_mapping_always_has_priority():
    scorecard = _persist("q82-verified")
    member = _member("q82-verified", "Mario Rossi", "WF-MARIO")
    put_mapping(organization_id="q82-verified", external_id=FIRST, workforce_member_id=member, actor="admin", expected_updated_at=None, scorecard_id=scorecard.scorecard_id)
    preview = _preview("q82-verified", scorecard.scorecard_id, _source([[FIRST, "Mario Rossi"]]))
    row = next(item for item in preview.rows if item.transporter_external_id == FIRST)
    assert row.status == "ALREADY_VERIFIED"
    assert row.evidence_source == "VERIFIED_MAPPING"


def test_canonical_external_identifier_is_exact():
    scorecard = _persist("q82-exact")
    member = _member("q82-exact", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    row = next(item for item in _preview("q82-exact", scorecard.scorecard_id, source).rows if item.transporter_external_id == FIRST)
    assert row.status == "EXACT"
    assert row.proposed_workforce_member_id == member


def test_name_only_exact_unique_is_suggestion_never_exact():
    scorecard = _persist("q82-name")
    _member("q82-name", "Mario Rossi", "WF-MARIO")
    row = next(item for item in _preview("q82-name", scorecard.scorecard_id, _source([[FIRST, "Mario Rossi"]])).rows if item.transporter_external_id == FIRST)
    assert row.status == "SUGGESTED"
    assert row.evidence_source == "NAME_SUGGESTION"


def test_duplicate_tid_with_different_drivers_is_conflict():
    scorecard = _persist("q82-duplicate")
    preview = _preview("q82-duplicate", scorecard.scorecard_id, _source([[FIRST, "Mario"], [FIRST, "Giulia"]]))
    row = next(item for item in preview.rows if item.transporter_external_id == FIRST)
    assert row.status == "CONFLICT"
    assert preview.coverage.conflicts == 1


def test_ambiguous_workforce_name_is_conflict():
    scorecard = _persist("q82-homonym")
    _member("q82-homonym", "Mario Rossi", "WF-1")
    _member("q82-homonym", "Mario Rossi", "WF-2")
    row = next(item for item in _preview("q82-homonym", scorecard.scorecard_id, _source([[FIRST, "Mario Rossi"]])).rows if item.transporter_external_id == FIRST)
    assert row.status == "CONFLICT"


def test_unknown_driver_is_unresolved():
    scorecard = _persist("q82-unresolved")
    row = next(item for item in _preview("q82-unresolved", scorecard.scorecard_id, _source([[FIRST, "Nessuno"]])).rows if item.transporter_external_id == FIRST)
    assert row.status == "UNRESOLVED"


def test_source_only_transporter_is_counted_but_not_returned_for_mapping():
    scorecard = _persist("q82-source-only")
    preview = _preview("q82-source-only", scorecard.scorecard_id, _source([["SOURCE-ONLY", "Mario"]]))
    assert preview.coverage.source_only == 1
    assert all(item.transporter_external_id != "SOURCE-ONLY" for item in preview.rows)


def test_exact_apply_creates_verified_mapping():
    scorecard = _persist("q82-apply")
    member = _member("q82-apply", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    preview = _preview("q82-apply", scorecard.scorecard_id, source)
    result = apply_exact_identity_matches(organization_id="q82-apply", scorecard_id=scorecard.scorecard_id, actor="admin", preview_token=preview.preview_token, source=source)
    assert result.applied == 1
    assert reconciliation_state("q82-apply", scorecard.scorecard_id).summary.matched == 1
    assert next(item for item in reconciliation_state("q82-apply", scorecard.scorecard_id).rows if item.transporter_external_id == FIRST).workforce_member_id == member


def test_exact_apply_is_idempotent_for_existing_verified_mapping():
    scorecard = _persist("q82-noop")
    _member("q82-noop", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    preview = _preview("q82-noop", scorecard.scorecard_id, source)
    apply_exact_identity_matches(organization_id="q82-noop", scorecard_id=scorecard.scorecard_id, actor="admin", preview_token=preview.preview_token, source=source)
    result = apply_exact_identity_matches(organization_id="q82-noop", scorecard_id=scorecard.scorecard_id, actor="admin", preview_token=preview.preview_token, source=source)
    assert result.applied == 0
    assert result.already_verified == 1


def test_conflict_blocks_entire_exact_batch():
    scorecard = _persist("q82-block")
    _member("q82-block", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"], [SECOND, "WF-A"], [SECOND, "WF-B"]], header=["T-ID", "external_identifier"])
    preview = _preview("q82-block", scorecard.scorecard_id, source)
    with pytest.raises(IdentitySourceError, match="conflitti"):
        apply_exact_identity_matches(organization_id="q82-block", scorecard_id=scorecard.scorecard_id, actor="admin", preview_token=preview.preview_token, source=source)
    assert reconciliation_state("q82-block", scorecard.scorecard_id).summary.matched == 0


def test_exact_apply_audit_contains_source_traceability():
    scorecard = _persist("q82-audit")
    _member("q82-audit", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"], filename="identity.xlsx")
    preview = _preview("q82-audit", scorecard.scorecard_id, source)
    apply_exact_identity_matches(organization_id="q82-audit", scorecard_id=scorecard.scorecard_id, actor="admin-audit", preview_token=preview.preview_token, source=source)
    with db_session() as conn:
        details = conn.execute("SELECT details FROM workforce_external_identity_events WHERE organization_id = ?", ("q82-audit",)).fetchone()["details"]
    for value in ("GENERIC_FILE_EXACT", "identity.xlsx", "Planning", "external_identifier"):
        assert value in details


def test_preview_never_persists_mappings_or_events():
    scorecard = _persist("q82-readonly")
    _member("q82-readonly", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    _preview("q82-readonly", scorecard.scorecard_id, source)
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) count FROM workforce_external_identities").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) count FROM workforce_external_identity_events").fetchone()["count"] == 0


def test_tampered_preview_token_is_rejected():
    scorecard = _persist("q82-token")
    _member("q82-token", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    preview = _preview("q82-token", scorecard.scorecard_id, source)
    with pytest.raises(IdentitySourceError, match="Token"):
        apply_exact_identity_matches(organization_id="q82-token", scorecard_id=scorecard.scorecard_id, actor="admin", preview_token=f"{preview.preview_token}x", source=source)


def test_organization_isolation_prevents_cross_tenant_workforce_resolution():
    scorecard_a = _persist("q82-org-a")
    _persist("q82-org-b")
    _member("q82-org-b", "Mario Segreto", "WF-SHARED")
    source = _source([[FIRST, "WF-SHARED"]], header=["T-ID", "external_identifier"])
    row = next(item for item in _preview("q82-org-a", scorecard_a.scorecard_id, source).rows if item.transporter_external_id == FIRST)
    assert row.status == "UNRESOLVED"


def test_other_organization_scorecard_is_not_selectable():
    scorecard_b = _persist("q82-scorecard-b")
    source = _source([[FIRST, "Mario"]])
    with pytest.raises(LookupError):
        _preview("q82-scorecard-a", scorecard_b.scorecard_id, source)


def test_q8_manual_mapping_flow_remains_available():
    scorecard = _persist("q82-manual")
    member = _member("q82-manual", "Mario Rossi", "WF-MARIO")
    result = put_mapping(organization_id="q82-manual", external_id=FIRST, workforce_member_id=member, actor="manual", expected_updated_at=None, scorecard_id=scorecard.scorecard_id)
    assert result.mapping_status == "MATCHED"


def test_mapping_applied_to_old_week_is_visible_in_other_history_weeks():
    old = _persist("q82-history", 45)
    new = _persist("q82-history", 47)
    member = _member("q82-history", "Mario Rossi", "WF-MARIO")
    source = _source([[FIRST, "WF-MARIO"]], header=["T-ID", "external_identifier"])
    preview = _preview("q82-history", old.scorecard_id, source)
    apply_exact_identity_matches(organization_id="q82-history", scorecard_id=old.scorecard_id, actor="admin", preview_token=preview.preview_token, source=source)
    for scorecard_id in (old.scorecard_id, new.scorecard_id):
        row = next(item for item in reconciliation_state("q82-history", scorecard_id).rows if item.transporter_external_id == FIRST)
        assert row.workforce_member_id == member


def test_planning_source_reuses_persisted_raw_rows_as_suggestions():
    scorecard = _persist("q82-planning")
    _member("q82-planning", "Mario Rossi", "WF-MARIO")
    with db_session() as conn:
        conn.execute(
            """INSERT INTO imports (organization_id, dataset_type, original_filename, imported_at, sheet_name, column_mapping, normalized_rows)
               VALUES (?, 'planning', 'Planning.xlsx', ?, 'Planning', '[]', ?)""",
            (
                "q82-planning",
                "2026-08-09T10:00:00+00:00",
                json.dumps([{
                    "row_number": 25,
                    "raw": {"T-ID": FIRST, "drivers": "Mario Rossi"},
                }]),
            ),
        )
    preview = preview_identity_source(organization_id="q82-planning", scorecard_id=scorecard.scorecard_id, use_planning=True)
    row = next(item for item in preview.rows if item.transporter_external_id == FIRST)
    assert preview.source.source_reference.startswith("planning-import:")
    assert row.status == "SUGGESTED"


def test_source_preview_api_accepts_selected_scorecard_and_csv():
    scorecard = _persist("test-organization")
    _member("test-organization", "Mario Rossi", "WF-MARIO")
    client = TestClient(app)
    response = client.post(
        "/api/dsp-quality/transporter-mappings/source-preview",
        data={"scorecard_id": scorecard.scorecard_id},
        files={"file": ("source.csv", f"T-ID,drivers\n{FIRST},Mario Rossi\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["coverage"]["suggestions"] == 1

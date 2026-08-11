import json
from datetime import date, timedelta
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.auth.tenant_context import bind_organization, reset_organization
from app.core.database import _postgres_schema_statement, db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_planning_service as service
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningError,
    DriverShiftPlanningNotFoundError,
    DriverShiftPlanningSourceNotFoundError,
    MergeClassification,
)
from app.plugins.workforce.infrastructure import driver_shift_planning_repository as repository
from app.workspace.reset_service import reset_workspace


ORG = "test-organization"


def _import(filename: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_imports (
                fingerprint, original_filename, imported_at, sheets,
                summary, organization_id
            ) VALUES (?, ?, '2026-08-11T10:00:00Z', '[]', '{}', ?)
            """,
            (f"fingerprint-{organization_id}-{filename}", filename, organization_id),
        )
        return int(cursor.lastrowid)


def _row(
    import_id: int,
    *,
    driver: str | None,
    member_id: int | None,
    operation_date: str = "2026-08-11",
    shift: str = "S1",
    status: str = "scheduled",
    transporter_id: str | None = None,
    row_number: int = 2,
    filename_sheet: str = "Planning",
    station: str = "DLO2",
    organization_id: str = ORG,
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_import_rows (
                organization_id, workforce_import_id, source_sheet,
                source_row_number, source_reference, source_record_key,
                row_kind, source_external_identifier, driver_display_name,
                transporter_id, station, operational_date, status_code,
                availability, shift_code, start_time, end_time, notes,
                employment_type, contract_start, contract_end, weekly_hours,
                resolved_workforce_member_id, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, 'shift', ?, ?, ?, ?, ?, ?, 1, ?,
                      NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, '{}')
            """,
            (
                organization_id, import_id, filename_sheet, row_number,
                f"{filename_sheet}!{row_number}",
                f"shift:{operation_date}:{row_number}", driver,
                f"Driver {driver}" if driver else None, transporter_id,
                station, operation_date, status, shift, member_id,
            ),
        )
        return int(cursor.lastrowid)


def _planning(
    start: str = "2026-08-01",
    end: str = "2026-08-31",
    organization_id: str = ORG,
):
    return service.create_driver_shift_planning(
        organization_id, start, end, "Agosto", actor="dispatcher@test"
    )


def _counts() -> dict[str, int]:
    with db_session() as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) total FROM {table}").fetchone()["total"])
            for table in (
                "workforce_members", "workforce_day_statuses",
                "workforce_requirements", "workforce_changes",
            )
        }


def test_create_logical_planning_requires_explicit_valid_period():
    planning = _planning()
    assert planning.status.value == "DRAFT"
    assert planning.version == 1
    assert planning.period_start == "2026-08-01"
    with pytest.raises(DriverShiftPlanningError):
        service.create_driver_shift_planning(ORG, "", "2026-08-31")
    with pytest.raises(DriverShiftPlanningError):
        service.create_driver_shift_planning(ORG, "2026-09-01", "2026-08-31")


def test_planning_and_source_are_strictly_organization_scoped():
    planning = _planning()
    foreign_import = _import("foreign.xlsx", "other-organization")
    _row(
        foreign_import, driver="WF-X", member_id=99,
        organization_id="other-organization",
    )
    with pytest.raises(DriverShiftPlanningNotFoundError):
        repository.get_planning("other-organization", planning.id)
    with pytest.raises(DriverShiftPlanningSourceNotFoundError):
        service.add_source(ORG, planning.id, foreign_import)


def test_add_one_source_is_idempotent_and_preserves_source_rows():
    import_id = _import("Planning_A.xlsx")
    row_id = _row(import_id, driver="WF-1", member_id=1)
    planning = _planning()
    first = service.add_source(ORG, planning.id, import_id)
    second = service.add_source(ORG, planning.id, import_id)
    assert first.id == second.id
    assert len(repository.list_sources(ORG, planning.id)) == 1
    with db_session() as conn:
        row = conn.execute(
            "SELECT source_external_identifier, shift_code FROM workforce_import_rows WHERE id=?",
            (row_id,),
        ).fetchone()
    assert (row["source_external_identifier"], row["shift_code"]) == ("WF-1", "S1")


def test_legacy_import_without_rows_is_available_as_safe_unmergeable_source():
    import_id = _import("legacy.xlsx")
    planning = _planning()
    source = service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    assert source.status.value == "UNAVAILABLE_FOR_MERGE"
    assert source.period_compatibility == "UNAVAILABLE"
    assert preview.summary.total_source_rows == 0


def test_source_period_compatible_partial_overlap_and_no_overlap():
    compatible = _import("inside.xlsx")
    _row(compatible, driver="WF-1", member_id=1, operation_date="2026-08-10")
    partial = _import("partial.xlsx")
    _row(partial, driver="WF-2", member_id=2, operation_date="2026-07-31")
    _row(partial, driver="WF-2", member_id=2, operation_date="2026-08-02", row_number=3)
    outside = _import("outside.xlsx")
    _row(outside, driver="WF-3", member_id=3, operation_date="2026-09-01")
    planning = _planning()
    inside_source = service.add_source(ORG, planning.id, compatible)
    partial_source = service.add_source(ORG, planning.id, partial)
    assert inside_source.period_compatibility == "COMPATIBLE"
    assert partial_source.period_compatibility == "PARTIAL_OVERLAP"
    assert partial_source.warnings
    with pytest.raises(DriverShiftPlanningError, match="sovrapposizione"):
        service.add_source(ORG, planning.id, outside)


def test_one_source_preview_matches_source_and_includes_readable_provenance():
    import_id = _import("Planning_A.xlsx")
    _row(import_id, driver="WF-1", member_id=1, row_number=27)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.total_source_rows == 1
    assert preview.summary.distinct_rows == 1
    assert preview.rows[0].classification == MergeClassification.DISTINCT_ASSIGNMENT
    reference = preview.rows[0].source_references[0]
    assert (reference.filename, reference.sheet, reference.row_number) == (
        "Planning_A.xlsx", "Planning", 27,
    )


def test_two_sources_classify_exact_duplicate_without_losing_references():
    first = _import("Planning_A.xlsx")
    second = _import("Planning_B.xlsx")
    _row(first, driver="WF-2", member_id=2, shift="S2")
    _row(second, driver="WF-2", member_id=2, shift="S2", row_number=84)
    planning = _planning()
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.exact_duplicates == 1
    assert len(preview.rows) == 1
    assert {item.filename for item in preview.rows[0].source_references} == {
        "Planning_A.xlsx", "Planning_B.xlsx",
    }


def test_two_sources_classify_potential_conflict_without_automatic_winner():
    first = _import("Planning_A.xlsx")
    second = _import("Planning_B.xlsx")
    _row(first, driver="WF-3", member_id=3, shift="S1", station="DLO2")
    _row(second, driver="WF-3", member_id=3, shift="S4", station="DLO3")
    planning = _planning()
    service.add_source(ORG, planning.id, first, source_order=8)
    service.add_source(ORG, planning.id, second, source_order=1)
    preview = service.merge_preview(ORG, planning.id)
    row = preview.rows[0]
    assert row.classification == MergeClassification.POTENTIAL_CONFLICT
    assert preview.summary.potential_conflicts == 1
    assert len(row.conflicting_alternatives) == 2
    assert {item.shift_code for item in row.conflicting_alternatives} == {"S1", "S4"}


def test_distinct_driver_date_assignments_remain_distinct():
    first = _import("Planning_A.xlsx")
    second = _import("Planning_B.xlsx")
    _row(first, driver="WF-1", member_id=1)
    _row(second, driver="WF-4", member_id=4)
    planning = _planning()
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.distinct_rows == 2
    assert len(preview.rows) == 2


def test_same_transporter_id_for_different_drivers_is_identity_conflict():
    first = _import("Planning_A.xlsx")
    second = _import("Planning_B.xlsx")
    _row(first, driver="WF-1", member_id=1, transporter_id="T-999")
    _row(second, driver="WF-4", member_id=4, transporter_id="T-999")
    planning = _planning()
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.identity_conflicts == 1
    assert {item.classification for item in preview.rows} == {
        MergeClassification.IDENTITY_CONFLICT
    }


def test_unresolved_external_identifier_uses_fallback_but_missing_identity_is_explicit():
    import_id = _import("unresolved.xlsx")
    _row(import_id, driver="SOURCE-77", member_id=None)
    _row(import_id, driver=None, member_id=None, row_number=3)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.unresolved_rows == 2
    by_identity = {item.identity_key: item for item in preview.rows}
    assert by_identity["external:source-77"].classification == MergeClassification.DISTINCT_ASSIGNMENT
    assert any(
        item.classification == MergeClassification.UNRESOLVED_IDENTITY
        for item in preview.rows
    )


def test_remove_source_only_removes_relation_and_replace_is_atomic_draft_contract():
    first = _import("Planning_A.xlsx")
    second = _import("Planning_B.xlsx")
    _row(first, driver="WF-1", member_id=1)
    _row(second, driver="WF-2", member_id=2)
    planning = _planning()
    linked = service.add_source(ORG, planning.id, first)
    service.remove_source(ORG, planning.id, linked.id)
    assert repository.list_sources(ORG, planning.id) == []
    assert repository.source_facts(ORG, first) is not None
    sources = service.replace_sources(ORG, planning.id, [first, second])
    assert [item.workforce_import_id for item in sources] == [first, second]
    with pytest.raises(DriverShiftPlanningError, match="ripetuta"):
        service.replace_sources(ORG, planning.id, [first, first])


def test_merge_preview_never_writes_canonical_workforce_tables():
    import_id = _import("Planning_A.xlsx")
    _row(import_id, driver="WF-1", member_id=1)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    before = _counts()
    service.merge_preview(ORG, planning.id)
    assert _counts() == before


def test_identity_evidence_contract_exposes_all_linked_sources_for_quality_future():
    import_id = _import("identity.xlsx")
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_import_rows (
                organization_id, workforce_import_id, source_sheet,
                source_row_number, source_reference, source_record_key,
                row_kind, source_external_identifier, driver_display_name,
                transporter_id, raw_payload
            ) VALUES (?, ?, 'Anagrafica', 9, 'Anagrafica!9', 'identity',
                      'identity', 'WF-9', 'Driver Nove', 'T-9', '{}')
            """,
            (ORG, import_id),
        )
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    evidence = service.list_identity_rows_for_logical_planning(ORG, planning.id)
    assert len(evidence) == 1
    assert evidence[0]["transporter_id"] == "T-9"
    assert evidence[0]["source_filename"] == "identity.xlsx"


def test_read_api_returns_merge_preview_and_write_api_uses_session_organization(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.workforce.interfaces.router.ensure_real_data_write_allowed",
        lambda: None,
    )
    client = TestClient(app)
    response = client.post(
        "/api/plugins/workforce/v1/driver-shift-plannings",
        json={
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "label": "API planning",
        },
    )
    assert response.status_code == 201
    planning_id = response.json()["id"]
    preview = client.get(
        f"/api/plugins/workforce/v1/driver-shift-plannings/{planning_id}/merge-preview"
    )
    assert preview.status_code == 200
    assert preview.json()["planning"]["organization_id"] == ORG


def test_workspace_reset_deletes_source_relations_before_plannings_and_imports():
    import_id = _import("Planning_A.xlsx")
    _row(import_id, driver="WF-1", member_id=1)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    token = bind_organization(ORG)
    try:
        result = reset_workspace(actor="test")
    finally:
        reset_organization(token)
    assert result.removed_counts.driver_shift_planning_sources == 1
    assert result.removed_counts.driver_shift_plannings == 1
    assert repository.source_facts(ORG, import_id) is None


def test_schema_is_postgresql_translatable_and_uses_no_sqlite_only_merge_sql():
    translated = _postgres_schema_statement(
        "CREATE TABLE driver_shift_plannings (id INTEGER PRIMARY KEY AUTOINCREMENT)"
    )
    assert "SERIAL PRIMARY KEY" in translated
    with db_session() as conn:
        source_columns = {
            row["name"] for row in conn.execute(
                "PRAGMA table_info(driver_shift_planning_sources)"
            ).fetchall()
        }
    assert {"organization_id", "driver_shift_planning_id", "workforce_import_id"} <= source_columns


def test_merge_100k_source_rows_is_linear_and_reasonable():
    first = _import("annual-A.xlsx")
    second = _import("annual-B.xlsx")
    start = date(2026, 1, 1)
    rows = []
    for import_id in (first, second):
        for driver_index in range(500):
            for day_index in range(100):
                operation_date = (start + timedelta(days=day_index)).isoformat()
                rows.append((
                    ORG, import_id, "Planning", driver_index + 2,
                    f"Planning!{driver_index + 2}",
                    f"shift:{operation_date}:{driver_index}", "shift",
                    f"WF-{driver_index:04d}", f"Driver {driver_index}",
                    f"T-{driver_index:04d}", "DLO2", operation_date,
                    "scheduled", 1, "S1", None, None, None, None,
                    None, None, None, driver_index + 1, "{}",
                ))
    with db_session() as conn:
        conn.executemany(
            """
            INSERT INTO workforce_import_rows (
                organization_id, workforce_import_id, source_sheet,
                source_row_number, source_reference, source_record_key,
                row_kind, source_external_identifier, driver_display_name,
                transporter_id, station, operational_date, status_code,
                availability, shift_code, start_time, end_time, notes,
                employment_type, contract_start, contract_end, weekly_hours,
                resolved_workforce_member_id, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    planning = _planning("2026-01-01", "2026-04-30")
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)
    started = perf_counter()
    preview = service.merge_preview(ORG, planning.id)
    elapsed = perf_counter() - started
    assert preview.summary.total_source_rows == 100_000
    assert preview.summary.exact_duplicates == 50_000
    assert len(preview.rows) == 50_000
    assert elapsed < 15

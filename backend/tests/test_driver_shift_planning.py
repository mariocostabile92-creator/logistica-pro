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
    DriverShiftPlanningConflictError,
    DriverShiftPlanningPublishBlockedError,
    DriverShiftPlanningResolutionType,
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


def _member(external_identifier: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'test', '2026-08-11T09:00:00Z',
                      '2026-08-11T09:00:00Z', ?)
            """,
            (external_identifier, f"Driver {external_identifier}", organization_id),
        )
        return int(cursor.lastrowid)


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


def test_unresolved_external_identifier_is_explicit_until_canonical_member_exists():
    import_id = _import("unresolved.xlsx")
    _row(import_id, driver="SOURCE-77", member_id=None)
    _row(import_id, driver=None, member_id=None, row_number=3)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    assert preview.summary.unresolved_rows == 2
    by_identity = {item.identity_key: item for item in preview.rows}
    assert by_identity["external:source-77"].classification == MergeClassification.UNRESOLVED_IDENTITY
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


def test_q4_import_reference_api_returns_scoped_source_without_changing_import_contract():
    import_id = _import("api-reference.xlsx")
    client = TestClient(app)

    response = client.get(
        "/api/plugins/workforce/v1/driver-shift-plannings/import-reference",
        params={"fingerprint": f"fingerprint-{ORG}-api-reference.xlsx"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "workforce_import_id": import_id,
        "fingerprint": f"fingerprint-{ORG}-api-reference.xlsx",
        "original_filename": "api-reference.xlsx",
        "imported_at": "2026-08-11T10:00:00Z",
    }


def test_q4_current_api_returns_current_draft_or_null():
    client = TestClient(app)
    empty = client.get(
        "/api/plugins/workforce/v1/driver-shift-plannings/current"
    )
    assert empty.status_code == 200
    assert empty.json() is None

    planning = _planning()
    current = client.get(
        "/api/plugins/workforce/v1/driver-shift-plannings/current"
    )
    assert current.status_code == 200
    assert current.json()["id"] == planning.id


def test_workspace_reset_deletes_source_relations_before_plannings_and_imports():
    member_id = _member("WF-RESET")
    import_id = _import("Planning_A.xlsx")
    selected_row = _row(import_id, driver="WF-RESET", member_id=member_id, shift="A")
    second_import = _import("Planning_B.xlsx")
    _row(second_import, driver="WF-RESET", member_id=member_id, shift="B")
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    service.add_source(ORG, planning.id, second_import)
    preview = service.merge_preview(ORG, planning.id)
    service.resolve_conflict(
        ORG, planning.id, preview.rows[0].conflict_key,
        DriverShiftPlanningResolutionType.USE_SOURCE_ROW,
        preview.planning.version, selected_source_row_id=selected_row,
    )
    preview = service.merge_preview(ORG, planning.id)
    service.publish_driver_shift_planning(
        ORG, planning.id, preview.planning.version, preview.preview_fingerprint,
    )
    token = bind_organization(ORG)
    try:
        result = reset_workspace(actor="test")
    finally:
        reset_organization(token)
    assert result.removed_counts.driver_shift_planning_sources == 2
    assert result.removed_counts.driver_shift_planning_resolutions == 1
    assert result.removed_counts.driver_shift_planning_published_rows == 1
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


def test_q4_get_list_and_current_planning_are_scoped_and_deterministic():
    first = _planning("2026-01-01", "2026-01-31")
    second = _planning("2026-02-01", "2026-02-28")
    foreign = _planning(
        "2026-03-01", "2026-03-31", organization_id="other-organization"
    )
    collection = service.list_driver_shift_plannings(ORG)
    assert [item.id for item in collection.items] == [second.id, first.id]
    assert collection.current.id == second.id
    assert service.current_driver_shift_planning(ORG).id == second.id
    assert service.get_driver_shift_planning(ORG, first.id).id == first.id
    assert foreign.id not in {item.id for item in collection.items}
    with pytest.raises(DriverShiftPlanningNotFoundError):
        service.get_driver_shift_planning(ORG, foreign.id)


def test_q4_import_reference_resolves_fingerprint_only_inside_organization():
    own_id = _import("Q4-source.xlsx")
    _import("Q4-source.xlsx", organization_id="other-organization")
    fingerprint = f"fingerprint-{ORG}-Q4-source.xlsx"

    reference = service.resolve_import_reference(ORG, fingerprint)

    assert reference["workforce_import_id"] == own_id
    assert reference["original_filename"] == "Q4-source.xlsx"
    with pytest.raises(DriverShiftPlanningSourceNotFoundError):
        service.resolve_import_reference("other-organization", fingerprint)


def test_q4_preview_pagination_filter_search_and_summary_are_invariant():
    first = _import("Q4_A.xlsx")
    second = _import("Q4_B.xlsx")
    _row(first, driver="MARIO-1", member_id=1, transporter_id="T-MARIO", row_number=2)
    _row(first, driver="ANNA-2", member_id=2, transporter_id="T-ANNA", row_number=3)
    _row(second, driver="MARIO-1", member_id=1, transporter_id="T-MARIO", row_number=8)
    _row(second, driver="ANNA-2", member_id=2, transporter_id="T-ANNA", shift="S9", row_number=9)
    _row(second, driver="LUCA-3", member_id=3, transporter_id="T-LUCA", row_number=10)
    planning = _planning()
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)

    page = service.merge_preview(ORG, planning.id, limit=1, offset=0)
    second_page = service.merge_preview(ORG, planning.id, limit=1, offset=1)
    exact = service.merge_preview(
        ORG, planning.id,
        classification=MergeClassification.EXACT_DUPLICATE,
        limit=10,
    )
    driver_search = service.merge_preview(
        ORG, planning.id, search="Driver MARIO-1", limit=10
    )
    tid_search = service.merge_preview(
        ORG, planning.id, search="T-ANNA", limit=10
    )

    assert page.filtered_rows == 3
    assert page.has_more is True
    assert second_page.offset == 1
    assert page.summary == second_page.summary == exact.summary
    assert page.summary.unified_rows == 3
    assert exact.filtered_rows == 1
    assert exact.rows[0].classification == MergeClassification.EXACT_DUPLICATE
    assert driver_search.filtered_rows == 1
    assert driver_search.rows[0].source_external_identifier == "MARIO-1"
    assert tid_search.filtered_rows == 1
    assert tid_search.rows[0].source_external_identifier == "ANNA-2"


def test_q4_add_remove_and_replace_recalculate_preview_without_canonical_writes():
    first = _import("Q4_A.xlsx")
    second = _import("Q4_B.xlsx")
    _row(first, driver="WF-1", member_id=1)
    _row(second, driver="WF-2", member_id=2)
    planning = _planning()
    before = _counts()
    linked = service.add_source(ORG, planning.id, first)
    assert service.merge_preview(ORG, planning.id).summary.total_source_rows == 1
    service.add_source(ORG, planning.id, second)
    assert service.merge_preview(ORG, planning.id).summary.total_source_rows == 2
    service.remove_source(ORG, planning.id, linked.id)
    assert service.merge_preview(ORG, planning.id).summary.total_source_rows == 1
    service.replace_sources(ORG, planning.id, [first])
    assert service.merge_preview(ORG, planning.id).summary.total_source_rows == 1
    assert _counts() == before


def test_q5_api_exposes_read_replace_preview_resolution_and_publish(monkeypatch):
    monkeypatch.setattr(
        "app.plugins.workforce.interfaces.router.ensure_real_data_write_allowed",
        lambda: None,
    )
    import_id = _import("Q4_API.xlsx")
    _row(import_id, driver="WF-API", member_id=7, transporter_id="T-API")
    planning = _planning()
    client = TestClient(app)

    collection = client.get("/api/plugins/workforce/v1/driver-shift-plannings")
    detail = client.get(
        f"/api/plugins/workforce/v1/driver-shift-plannings/{planning.id}"
    )
    replaced = client.put(
        f"/api/plugins/workforce/v1/driver-shift-plannings/{planning.id}/sources",
        json={"workforce_import_ids": [import_id]},
    )
    preview = client.get(
        f"/api/plugins/workforce/v1/driver-shift-plannings/{planning.id}/merge-preview",
        params={"search": "T-API", "limit": 1, "offset": 0},
    )
    paths = app.openapi()["paths"]

    assert collection.status_code == detail.status_code == replaced.status_code == 200
    assert collection.json()["current"]["id"] == planning.id
    assert replaced.json()[0]["row_count"] == 1
    assert preview.status_code == 200
    assert preview.json()["filtered_rows"] == 1
    planning_paths = [path for path in paths if "driver-shift-plannings" in path]
    assert any(path.endswith("/publish") for path in planning_paths)
    assert any("/conflicts/" in path for path in planning_paths)
    assert any(path.endswith("/new-revision") for path in planning_paths)


def test_q5_resolution_persists_survives_reload_and_rejects_stale_version():
    member_id = _member("WF-RESOLVE")
    first = _import("resolve-a.xlsx")
    second = _import("resolve-b.xlsx")
    first_row = _row(first, driver="WF-RESOLVE", member_id=member_id, shift="A")
    _row(second, driver="WF-RESOLVE", member_id=member_id, shift="B")
    planning = _planning()
    service.add_source(ORG, planning.id, first)
    service.add_source(ORG, planning.id, second)
    preview = service.merge_preview(ORG, planning.id)
    resolution = service.resolve_conflict(
        ORG, planning.id, preview.rows[0].conflict_key,
        DriverShiftPlanningResolutionType.USE_SOURCE_ROW,
        preview.planning.version, selected_source_row_id=first_row, actor="dispatcher@test",
    )
    reloaded = service.merge_preview(ORG, planning.id)
    assert resolution.selected_source_row_id == first_row
    assert reloaded.rows[0].resolved is True
    assert reloaded.summary.conflicts_resolved == 1
    with pytest.raises(DriverShiftPlanningConflictError):
        service.resolve_conflict(
            ORG, planning.id, preview.rows[0].conflict_key,
            DriverShiftPlanningResolutionType.EXCLUDE,
            preview.planning.version - 1, actor="dispatcher@test",
        )


def test_q5_unresolved_identity_blocks_then_allows_scoped_manual_association():
    member_id = _member("WF-MANUAL")
    foreign_member = _member("WF-MANUAL", "other-organization")
    import_id = _import("unresolved-publish.xlsx")
    row_id = _row(import_id, driver="LEGACY NAME", member_id=None)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    with pytest.raises(DriverShiftPlanningPublishBlockedError):
        service.publish_driver_shift_planning(
            ORG, planning.id, preview.planning.version, preview.preview_fingerprint,
        )
    with pytest.raises(DriverShiftPlanningError):
        service.resolve_conflict(
            ORG, planning.id, preview.rows[0].conflict_key,
            DriverShiftPlanningResolutionType.USE_SOURCE_ROW,
            preview.planning.version, selected_source_row_id=row_id,
            workforce_member_id=foreign_member,
        )
    service.resolve_conflict(
        ORG, planning.id, preview.rows[0].conflict_key,
        DriverShiftPlanningResolutionType.USE_SOURCE_ROW,
        preview.planning.version, selected_source_row_id=row_id,
        workforce_member_id=member_id,
    )
    ready = service.merge_preview(ORG, planning.id)
    assert ready.summary.ready_to_publish is True


def test_q5_single_source_publish_updates_canonical_preserves_tid_and_outside_period():
    member_id = _member("WF-PUBLISH")
    import_id = _import("single-publish.xlsx")
    _row(import_id, driver="WF-PUBLISH", member_id=member_id, shift="S1", transporter_id="T-900")
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    with db_session() as conn:
        conn.executemany(
            """INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability, source_reference,
                observed_or_confirmed, updated_at, organization_id
            ) VALUES (?, ?, 'legacy', 0, 'legacy', 'confirmed',
                      '2026-08-01T00:00:00Z', ?)""",
            [(member_id, "2026-07-31", ORG), (member_id, "2026-08-12", ORG)],
        )
    preview = service.merge_preview(ORG, planning.id)
    result = service.publish_driver_shift_planning(
        ORG, planning.id, preview.planning.version, preview.preview_fingerprint,
        actor="dispatcher@test",
    )
    assert result.planning.status.value == "ACTIVE"
    with db_session() as conn:
        statuses = conn.execute(
            "SELECT date, shift_code, source_reference FROM workforce_day_statuses WHERE organization_id=? ORDER BY date",
            (ORG,),
        ).fetchall()
        published = conn.execute(
            "SELECT transporter_id, provenance_summary FROM driver_shift_planning_published_rows WHERE organization_id=?",
            (ORG,),
        ).fetchone()
        audit = conn.execute(
            "SELECT reason FROM workforce_changes WHERE organization_id=? ORDER BY id",
            (ORG,),
        ).fetchall()
    assert [(row["date"], row["shift_code"]) for row in statuses] == [
        ("2026-07-31", None), ("2026-08-11", "S1"),
    ]
    assert statuses[1]["source_reference"].startswith("driver_shift_planning:")
    assert published["transporter_id"] == "T-900"
    assert json.loads(published["provenance_summary"])[0]["source_row_id"] > 0
    assert "driver_shift_planning_published" in {row["reason"] for row in audit}
    with pytest.raises(DriverShiftPlanningError):
        service.add_source(ORG, planning.id, import_id)


def test_q5_multi_source_resolution_replace_scope_supersede_and_revision():
    member_id = _member("WF-MULTI")
    first = _import("multi-a.xlsx")
    second = _import("multi-b.xlsx")
    first_row = _row(first, driver="WF-MULTI", member_id=member_id, shift="A")
    _row(second, driver="WF-MULTI", member_id=member_id, shift="B")
    old = _planning()
    service.add_source(ORG, old.id, first)
    old_preview = service.merge_preview(ORG, old.id)
    service.publish_driver_shift_planning(
        ORG, old.id, old_preview.planning.version, old_preview.preview_fingerprint,
    )
    revision = service.create_new_revision(ORG, old.id, actor="dispatcher@test")
    assert revision.status.value == "DRAFT"
    assert revision.revision_of_planning_id == old.id
    service.replace_sources(ORG, revision.id, [first, second])
    preview = service.merge_preview(ORG, revision.id)
    service.resolve_conflict(
        ORG, revision.id, preview.rows[0].conflict_key,
        DriverShiftPlanningResolutionType.USE_SOURCE_ROW,
        preview.planning.version, selected_source_row_id=first_row,
    )
    ready = service.merge_preview(ORG, revision.id)
    published = service.publish_driver_shift_planning(
        ORG, revision.id, ready.planning.version, ready.preview_fingerprint,
    )
    assert old.id in published.superseded_planning_ids
    assert repository.get_planning(ORG, old.id).status.value == "SUPERSEDED"


def test_q5_preview_fingerprint_mismatch_and_transaction_failure_roll_back(monkeypatch):
    member_id = _member("WF-ROLLBACK")
    import_id = _import("rollback.xlsx")
    _row(import_id, driver="WF-ROLLBACK", member_id=member_id)
    planning = _planning()
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    with pytest.raises(DriverShiftPlanningConflictError):
        service.publish_driver_shift_planning(
            ORG, planning.id, preview.planning.version, "0" * 64,
        )
    monkeypatch.setattr(repository, "_apply_canonical_statuses", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        service.publish_driver_shift_planning(
            ORG, planning.id, preview.planning.version, preview.preview_fingerprint,
        )
    assert repository.get_planning(ORG, planning.id).status.value == "DRAFT"
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) total FROM driver_shift_planning_published_rows").fetchone()["total"] == 0
        assert conn.execute("SELECT COUNT(*) total FROM workforce_day_statuses").fetchone()["total"] == 0


def test_q5_publish_48k_annual_rows_uses_batch_projection_and_canonical_apply():
    driver_count = 160
    day_count = 300
    with db_session() as conn:
        conn.executemany(
            """INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'performance', '2026-01-01T00:00:00Z',
                      '2026-01-01T00:00:00Z', ?)""",
            [(f"WF-{index:04d}", f"Driver {index}", ORG) for index in range(driver_count)],
        )
        members = conn.execute(
            "SELECT id, external_identifier FROM workforce_members WHERE organization_id=?",
            (ORG,),
        ).fetchall()
    member_by_external = {row["external_identifier"]: int(row["id"]) for row in members}
    import_id = _import("annual-publish.xlsx")
    start = date(2026, 1, 1)
    rows = []
    for driver_index in range(driver_count):
        external = f"WF-{driver_index:04d}"
        for day_index in range(day_count):
            operation_date = (start + timedelta(days=day_index)).isoformat()
            rows.append((
                ORG, import_id, "Planning", driver_index + 2,
                f"Planning!{driver_index + 2}", f"shift:{operation_date}:{driver_index}",
                "shift", external, f"Driver {driver_index}", f"T-{driver_index:04d}",
                "DLO2", operation_date, "scheduled", 1, "S1", None, None, None,
                None, None, None, None, member_by_external[external], "{}",
            ))
    with db_session() as conn:
        conn.executemany(
            """INSERT INTO workforce_import_rows (
                organization_id, workforce_import_id, source_sheet,
                source_row_number, source_reference, source_record_key,
                row_kind, source_external_identifier, driver_display_name,
                transporter_id, station, operational_date, status_code,
                availability, shift_code, start_time, end_time, notes,
                employment_type, contract_start, contract_end, weekly_hours,
                resolved_workforce_member_id, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    planning = _planning("2026-01-01", "2026-12-31")
    service.add_source(ORG, planning.id, import_id)
    preview = service.merge_preview(ORG, planning.id)
    started = perf_counter()
    publication = service.publish_driver_shift_planning(
        ORG, planning.id, preview.planning.version, preview.preview_fingerprint,
    )
    elapsed = perf_counter() - started
    assert publication.published_rows == 48_000
    with db_session() as conn:
        canonical = conn.execute(
            "SELECT COUNT(*) total FROM workforce_day_statuses WHERE organization_id=?",
            (ORG,),
        ).fetchone()["total"]
    assert canonical == 48_000
    assert elapsed < 20

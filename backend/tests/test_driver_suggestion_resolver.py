from uuid import uuid4

import pytest

from app.core.database import db_session
from app.plugins.fleet.damage.application.driver_suggestion_resolver import (
    resolve_driver_suggestion,
)
from app.plugins.fleet.damage.domain.driver_suggestion import (
    DriverSuggestionStatus,
)


DAY = "2026-08-08"
NOW = f"{DAY}T10:00:00+00:00"


def _member(organization_id: str, identifier: str, name: str) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'suggestion-test', ?, ?)
            """,
            (organization_id, identifier, name, NOW, NOW),
        ).lastrowid)


def _asset(organization_id: str, plate: str) -> int:
    with db_session() as conn:
        return int(conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category,
                status, availability, notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'Furgone', 'active', 'available', NULL, '[]', ?, ?)
            """,
            (organization_id, f"ASSET-{plate}", plate, NOW, NOW),
        ).lastrowid)


def _movement(
    organization_id: str,
    vehicle_id: int,
    plate: str,
    driver_identifier: str,
) -> None:
    session_id = str(uuid4())
    movement_id = str(uuid4())
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, status, created_at, expires_at,
                completed_at, organization_id, source, lifecycle_status,
                operational_date, warnings_json
            ) VALUES (?, 'token', 'check_out', ?, ?, ?, 'completed', ?, ?, ?,
                      ?, 'driver', 'completed', ?, '[]')
            """,
            (
                session_id, vehicle_id, plate, driver_identifier,
                NOW, NOW, NOW, organization_id, DAY,
            ),
        )
        conn.execute(
            """
            INSERT INTO asset_movements (
                id, session_id, schema_version, organization_id,
                operational_unit_id, asset_id, plate_snapshot,
                declared_driver_identifier, operation_type, occurred_at,
                timezone, odometer_km, fuel_percentage, anomaly_present,
                client_submission_id, created_at
            ) VALUES (?, ?, '1.0', ?, 'DLO1', ?, ?, ?, 'check_out', ?,
                      'Europe/Rome', 1000, 80, 0, ?, ?)
            """,
            (
                movement_id, session_id, organization_id, vehicle_id, plate,
                driver_identifier, NOW, f"submission-{movement_id}", NOW,
            ),
        )


def _planning(
    organization_id: str,
    plate: str,
    driver_identifier: str,
    status: str,
) -> int:
    with db_session() as conn:
        planning_import = conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'planning', 'planning.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid
        fleet_import = conn.execute(
            """
            INSERT INTO imports (
                organization_id, dataset_type, original_filename, imported_at,
                column_mapping, normalized_rows
            ) VALUES (?, 'fleet', 'fleet.csv', ?, '{}', '[]')
            """,
            (organization_id, NOW),
        ).lastrowid
        planning_id = int(conn.execute(
            """
            INSERT INTO plannings (
                organization_id, operation_date, station,
                source_planning_import_id, source_fleet_import_id, status,
                version, reserve_threshold, configuration, summary, conflicts,
                generation_metadata, created_at, updated_at
            ) VALUES (?, ?, 'DLO1', ?, ?, ?, 1, 1, '{}', '{}', '[]', '{}', ?, ?)
            """,
            (
                organization_id, DAY, planning_import, fleet_import,
                status, NOW, NOW,
            ),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO assignments (
                planning_id, operation_date, station, route_id,
                driver_id, driver_name, vehicle_id, plate, assignment_status,
                assignment_source, confidence, reasons, data_used, warnings,
                alternatives, manual_override, confirmed, created_at, updated_at
            ) VALUES (?, ?, 'DLO1', ?, ?, ?, ?, ?, 'confirmed', 'manual', 1.0,
                      '[]', '[]', '[]', '[]', 0, 1, ?, ?)
            """,
            (
                planning_id, DAY, f"ROUTE-{planning_id}", driver_identifier,
                driver_identifier, plate, plate, NOW, NOW,
            ),
        )
    return planning_id


def test_unique_journal_driver_is_the_suggestion():
    member_id = _member("org-a", "DRV-A", "Driver A")
    vehicle_id = _asset("org-a", "AA001AA")
    _movement("org-a", vehicle_id, "AA001AA", "DRV-A")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.MATCH
    assert result.source == "journal"
    assert result.workforce_member_id == member_id


@pytest.mark.parametrize("planning_status", ["published", "confirmed"])
def test_authoritative_planning_is_used_when_journal_is_absent(planning_status):
    member_id = _member("org-a", "DRV-P", "Driver Planning")
    vehicle_id = _asset("org-a", "AA002AA")
    _planning("org-a", "AA002AA", "DRV-P", planning_status)

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.MATCH
    assert result.source == "planning"
    assert result.workforce_member_id == member_id
    assert any(f":{planning_status}:" in item for item in result.evidence)


def test_draft_planning_is_not_authoritative():
    _member("org-a", "DRV-D", "Driver Draft")
    vehicle_id = _asset("org-a", "AA003AA")
    _planning("org-a", "AA003AA", "DRV-D", "draft")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.NOT_FOUND


def test_published_planning_has_priority_over_newer_confirmed_planning():
    published_id = _member("org-a", "DRV-PUB", "Driver Published")
    _member("org-a", "DRV-CONF", "Driver Confirmed")
    vehicle_id = _asset("org-a", "AA010AA")
    _planning("org-a", "AA010AA", "DRV-PUB", "published")
    _planning("org-a", "AA010AA", "DRV-CONF", "confirmed")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.MATCH
    assert result.workforce_member_id == published_id
    assert result.source == "planning"


def test_same_journal_and_planning_driver_keeps_journal_priority():
    member_id = _member("org-a", "DRV-SAME", "Driver Coerente")
    vehicle_id = _asset("org-a", "AA004AA")
    _movement("org-a", vehicle_id, "AA004AA", "DRV-SAME")
    _planning("org-a", "AA004AA", "DRV-SAME", "published")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.MATCH
    assert result.source == "journal"
    assert result.conflict is False
    assert result.workforce_member_id == member_id
    assert result.journal_driver is not None
    assert result.planning_driver is not None


def test_different_journal_and_planning_drivers_are_a_conflict():
    journal_id = _member("org-a", "DRV-J", "Driver Journal")
    planning_id = _member("org-a", "DRV-P", "Driver Planning")
    vehicle_id = _asset("org-a", "AA005AA")
    _movement("org-a", vehicle_id, "AA005AA", "DRV-J")
    _planning("org-a", "AA005AA", "DRV-P", "confirmed")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.CONFLICT
    assert result.conflict is True
    assert result.journal_driver.workforce_member_id == journal_id
    assert result.planning_driver.workforce_member_id == planning_id


def test_multiple_incompatible_journal_drivers_are_ambiguous():
    _member("org-a", "DRV-1", "Driver Uno")
    _member("org-a", "DRV-2", "Driver Due")
    vehicle_id = _asset("org-a", "AA006AA")
    _movement("org-a", vehicle_id, "AA006AA", "DRV-1")
    _movement("org-a", vehicle_id, "AA006AA", "DRV-2")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.AMBIGUOUS
    assert result.matched is False


def test_multiple_unresolvable_journal_identifiers_are_ambiguous():
    vehicle_id = _asset("org-a", "AA009AA")
    _movement("org-a", vehicle_id, "AA009AA", "UNKNOWN-1")
    _movement("org-a", vehicle_id, "AA009AA", "UNKNOWN-2")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.AMBIGUOUS


def test_no_source_returns_not_found():
    vehicle_id = _asset("org-a", "AA007AA")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.NOT_FOUND


def test_foreign_organization_vehicle_does_not_leak():
    _member("org-b", "DRV-B", "Driver Organizzazione B")
    vehicle_id = _asset("org-b", "BB001BB")
    _movement("org-b", vehicle_id, "BB001BB", "DRV-B")
    _planning("org-b", "BB001BB", "DRV-B", "published")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.NOT_FOUND
    assert result.journal_driver is None
    assert result.planning_driver is None


def test_unresolvable_driver_identifier_never_creates_a_false_match():
    vehicle_id = _asset("org-a", "AA008AA")
    _movement("org-a", vehicle_id, "AA008AA", "UNKNOWN")

    result = resolve_driver_suggestion(
        organization_id="org-a", vehicle_id=vehicle_id, operational_date=DAY,
    )

    assert result.status is DriverSuggestionStatus.NOT_FOUND
    assert result.workforce_member_id is None


@pytest.mark.parametrize(
    ("organization_id", "vehicle_id", "operational_date"),
    [("", 1, DAY), ("org-a", 0, DAY), ("org-a", 1, "not-a-date")],
)
def test_invalid_input_is_rejected(
    organization_id,
    vehicle_id,
    operational_date,
):
    result = resolve_driver_suggestion(
        organization_id=organization_id,
        vehicle_id=vehicle_id,
        operational_date=operational_date,
    )
    assert result.status is DriverSuggestionStatus.INVALID

import pytest

from app.core.database import db_session
from app.plugins.workforce.application.driver_identity_resolver import (
    resolve_driver_identity,
)
from app.plugins.workforce.domain.driver_identity import (
    DriverIdentityResolutionStatus,
)
from app.plugins.workforce.infrastructure import read_repository


def _member(organization_id: str, identifier: str, name: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'identity-test', ?, ?)
            """,
            (
                organization_id,
                identifier,
                name,
                "2026-08-08T10:00:00+00:00",
                "2026-08-08T10:00:00+00:00",
            ),
        )
        return int(cursor.lastrowid)


def test_planning_identifier_resolves_workforce_member():
    member_id = _member("org-a", "DRV-001", "Mario Rossi")

    result = resolve_driver_identity(
        organization_id="org-a",
        driver_identifier="DRV-001",
        source="planning",
    )

    assert result.status is DriverIdentityResolutionStatus.MATCH
    assert result.matched is True
    assert result.workforce_member_id == member_id
    assert result.external_identifier == "DRV-001"
    assert result.display_name == "Mario Rossi"
    assert result.source == "planning"


def test_journal_identifier_resolves_direct_external_identifier():
    member_id = _member("org-a", "GDB-DRIVER-7", "Giulia Bianchi")

    result = resolve_driver_identity(
        organization_id="org-a",
        driver_identifier="  gdb-driver-7  ",
        source="journal",
    )

    assert result.status is DriverIdentityResolutionStatus.MATCH
    assert result.workforce_member_id == member_id
    assert result.external_identifier == "GDB-DRIVER-7"


def test_unknown_identifier_is_not_found_without_creating_a_member():
    with db_session() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_members"
        ).fetchone()["total"]

    result = resolve_driver_identity(
        organization_id="org-a",
        driver_identifier="UNKNOWN",
        source="journal",
    )

    with db_session() as conn:
        after = conn.execute(
            "SELECT COUNT(*) AS total FROM workforce_members"
        ).fetchone()["total"]
    assert result.status is DriverIdentityResolutionStatus.NOT_FOUND
    assert result.matched is False
    assert before == after


@pytest.mark.parametrize(
    ("organization_id", "driver_identifier", "source"),
    [
        ("org-a", "", "journal"),
        ("org-a", "   ", "planning"),
        ("", "DRV-001", "planning"),
        ("org-a", "DRV-001", "unsupported"),
        ("org-a", None, "journal"),
    ],
)
def test_invalid_input_is_reported(
    organization_id: str,
    driver_identifier: str | None,
    source: str,
):
    result = resolve_driver_identity(
        organization_id=organization_id,
        driver_identifier=driver_identifier,
        source=source,
    )

    assert result.status is DriverIdentityResolutionStatus.INVALID
    assert result.matched is False


def test_resolution_is_strictly_scoped_to_requested_organization():
    first_id = _member("org-a", "SHARED-001", "Driver Organizzazione A")
    _member("org-b", "SHARED-001", "Driver Organizzazione B")

    result = resolve_driver_identity(
        organization_id="org-a",
        driver_identifier="SHARED-001",
        source="planning",
    )

    assert result.status is DriverIdentityResolutionStatus.MATCH
    assert result.workforce_member_id == first_id
    assert result.display_name == "Driver Organizzazione A"


def test_multiple_compatible_candidates_are_ambiguous(monkeypatch):
    _member("org-a", "Driver-9", "Primo Driver")
    _member("org-a", "Driver-10", "Secondo Driver")
    candidates = read_repository.list_members("org-a")
    monkeypatch.setattr(
        read_repository,
        "find_members_by_external_identifier",
        lambda organization_id, external_identifier: candidates,
    )

    result = resolve_driver_identity(
        organization_id="org-a",
        driver_identifier="DRIVER-9",
        source="journal",
    )

    assert result.status is DriverIdentityResolutionStatus.AMBIGUOUS
    assert result.matched is False
    assert result.candidate_count == 2
    assert result.workforce_member_id is None

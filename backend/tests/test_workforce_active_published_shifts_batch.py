from contextlib import contextmanager

import pytest

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublishedRow,
)
from app.plugins.workforce.infrastructure import (
    driver_shift_planning_repository as repository,
)


ORG = "qa-active-published-shifts"
OTHER_ORG = "qa-active-published-shifts-other"
PERIOD_START = "2026-08-17"
PERIOD_END = "2026-08-23"
NOW = "2026-08-20T08:00:00+00:00"


def _member(identifier: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, capabilities, active,
                source_reference, created_at, updated_at, organization_id
            ) VALUES (?, ?, '[]', 1, 'active-published-shifts-test', ?, ?, ?)
            """,
            (identifier, f"Driver {identifier}", NOW, NOW, organization_id),
        )
        return int(cursor.lastrowid)


def _planning(status: str, organization_id: str = ORG) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status,
                version, created_at, created_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, 'qa@test', ?)
            """,
            (
                organization_id,
                f"Planning {status}",
                PERIOD_START,
                PERIOD_END,
                status,
                NOW,
                NOW,
            ),
        )
        return int(cursor.lastrowid)


def _published_row(
    planning_id: int,
    member_id: int,
    operation_date: str,
    *,
    shift_code: str | None = "C1",
    organization_id: str = ORG,
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_planning_published_rows (
                organization_id, driver_shift_planning_id, planning_version,
                workforce_member_id, operational_date, status_code,
                availability, shift_code, provenance_summary, published_at
            ) VALUES (?, ?, 1, ?, ?, 'scheduled', 1, ?, '[]', ?)
            """,
            (
                organization_id,
                planning_id,
                member_id,
                operation_date,
                shift_code,
                NOW,
            ),
        )
        return int(cursor.lastrowid)


def test_batch_returns_only_active_rows_inside_period_in_stable_order():
    first_member = _member("BATCH-A")
    second_member = _member("BATCH-B")
    active = _planning("ACTIVE")
    draft = _planning("DRAFT")
    superseded = _planning("SUPERSEDED")

    expected_ids = [
        _published_row(active, second_member, "2026-08-18", shift_code="SB"),
        _published_row(active, first_member, "2026-08-18", shift_code="SA"),
        _published_row(active, first_member, "2026-08-17", shift_code="C1"),
    ]
    _published_row(active, first_member, "2026-08-16")
    _published_row(active, first_member, "2026-08-24")
    _published_row(draft, first_member, "2026-08-19")
    _published_row(superseded, first_member, "2026-08-20")

    result = repository.list_active_published_shifts(
        ORG, PERIOD_START, PERIOD_END
    )

    assert all(isinstance(item, DriverShiftPlanningPublishedRow) for item in result)
    assert [item.id for item in result] == [
        expected_ids[2],
        expected_ids[1],
        expected_ids[0],
    ]
    assert [item.operational_date for item in result] == [
        "2026-08-17",
        "2026-08-18",
        "2026-08-18",
    ]


def test_batch_requires_planning_row_and_member_to_share_the_organization():
    local_member = _member("BATCH-LOCAL")
    foreign_member = _member("BATCH-FOREIGN", OTHER_ORG)
    local_planning = _planning("ACTIVE")
    foreign_planning = _planning("ACTIVE", OTHER_ORG)

    local_id = _published_row(local_planning, local_member, "2026-08-18")
    _published_row(local_planning, foreign_member, "2026-08-19")
    _published_row(
        foreign_planning,
        local_member,
        "2026-08-20",
        organization_id=OTHER_ORG,
    )

    local = repository.list_active_published_shifts(ORG, PERIOD_START, PERIOD_END)
    foreign = repository.list_active_published_shifts(
        OTHER_ORG, PERIOD_START, PERIOD_END
    )

    assert [item.id for item in local] == [local_id]
    assert foreign == []


def test_batch_validates_explicit_organization_and_period():
    with pytest.raises(ValueError, match="organization_id is required"):
        repository.list_active_published_shifts(" ", PERIOD_START, PERIOD_END)
    with pytest.raises(ValueError, match="period_end"):
        repository.list_active_published_shifts(
            ORG, PERIOD_END, PERIOD_START
        )


def test_legacy_single_member_reader_keeps_its_existing_dict_contract():
    member_id = _member("BATCH-LEGACY")
    active = _planning("ACTIVE")
    draft = _planning("DRAFT")
    active_id = _published_row(active, member_id, "2026-08-18")
    _published_row(draft, member_id, "2026-08-19")

    result = repository.list_published_shifts_for_workforce_member(
        ORG, member_id, PERIOD_START, PERIOD_END
    )

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["id"] == active_id


def test_batch_executes_exactly_one_query(monkeypatch):
    member_id = _member("BATCH-CALL-COUNT")
    active = _planning("ACTIVE")
    for offset in range(3):
        _published_row(active, member_id, f"2026-08-{17 + offset:02d}")

    real_db_session = db_session
    calls = {"queries": 0}

    class CountedConnection:
        def __init__(self, connection):
            self._connection = connection

        def execute(self, statement, parameters=()):
            calls["queries"] += 1
            return self._connection.execute(statement, parameters)

        def __getattr__(self, name):
            return getattr(self._connection, name)

    @contextmanager
    def counted_db_session():
        with real_db_session() as connection:
            yield CountedConnection(connection)

    monkeypatch.setattr(repository, "db_session", counted_db_session)

    result = repository.list_active_published_shifts(
        ORG, PERIOD_START, PERIOD_END
    )

    assert len(result) == 3
    assert calls == {"queries": 1}

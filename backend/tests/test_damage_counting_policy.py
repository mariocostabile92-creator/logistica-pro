from datetime import date

import pytest

from app.core.database import db_session
from app.plugins.fleet.damage.application import (
    damage_counter_service,
    damage_policy_service,
)
from app.plugins.fleet.damage.domain.damage_policy import (
    DamageCountingPeriod,
    DamagePolicy,
    is_damage_countable,
)
from app.plugins.fleet.damage.infrastructure import damage_policy_repository


REFERENCE_DATE = date(2026, 8, 8)
NOW = "2026-08-08T12:00:00+00:00"


def _member(organization_id: str, identifier: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                organization_id, external_identifier, display_name, role,
                capabilities, active, source_reference, created_at, updated_at
            ) VALUES (?, ?, ?, 'driver', '[]', 1, 'policy-test', ?, ?)
            """,
            (organization_id, identifier, f"Driver {identifier}", NOW, NOW),
        )
        return int(cursor.lastrowid)


def _asset(organization_id: str, suffix: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_assets (
                organization_id, external_identifier, plate, category, status,
                availability, notes, capabilities, created_at, updated_at
            ) VALUES (?, ?, ?, 'van', 'active', 'available', NULL, '[]', ?, ?)
            """,
            (organization_id, f"policy-asset-{suffix}", f"P{suffix}AA", NOW, NOW),
        )
        return int(cursor.lastrowid)


def _case(
    organization_id: str,
    member_id: int | None,
    status: str,
    occurred_at: str,
    suffix: str,
) -> int:
    asset_id = _asset(organization_id, suffix)
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO damage_cases (
                case_number, vehicle_id, occurred_at, created_at, updated_at,
                origin, description, severity, status,
                vehicle_operational_status, driver_workforce_member_id
            ) VALUES (?, ?, ?, ?, ?, 'manual', 'Policy test', 'media', ?,
                      'disponibile', ?)
            """,
            (f"DMG-POLICY-{suffix}", asset_id, occurred_at, NOW, NOW, status, member_id),
        )
        return int(cursor.lastrowid)


@pytest.mark.parametrize(
    ("damage_case", "expected"),
    [
        ({"status": "nuova", "driver_workforce_member_id": None}, False),
        ({"status": "annullata", "driver_workforce_member_id": 1}, False),
        ({"status": "in_valutazione", "driver_workforce_member_id": 1}, True),
        ({"status": "chiusa", "driver_workforce_member_id": 1}, True),
    ],
)
def test_countable_rule_uses_real_status_and_canonical_driver(damage_case, expected):
    assert is_damage_countable(damage_case) is expected


def test_default_policy_is_disabled_zero_and_all_time():
    policy = damage_policy_service.current_policy("organization-default")

    assert policy.enabled is False
    assert policy.free_events_count == 0
    assert policy.counting_period is DamageCountingPeriod.ALL_TIME


def test_policy_persistence_is_idempotent_and_organization_scoped():
    damage_policy_repository.init_schema()
    damage_policy_repository.init_schema()
    first = damage_policy_service.save_policy(DamagePolicy(
        organization_id="organization-a",
        enabled=True,
        free_events_count=1,
        counting_period=DamageCountingPeriod.CALENDAR_YEAR,
    ))
    damage_policy_service.save_policy(DamagePolicy(
        organization_id="organization-b",
        enabled=True,
        free_events_count=2,
        counting_period=DamageCountingPeriod.ROLLING_12_MONTHS,
    ))

    assert first.free_events_count == 1
    assert damage_policy_service.current_policy("organization-a").counting_period is DamageCountingPeriod.CALENDAR_YEAR
    assert damage_policy_service.current_policy("organization-b").free_events_count == 2
    with db_session() as conn:
        assert conn.execute("SELECT COUNT(*) AS total FROM damage_policies").fetchone()["total"] == 2


def test_disabled_policy_preserves_descriptive_count_without_thresholds():
    organization_id = "organization-disabled"
    member_id = _member(organization_id, "DISABLED")
    _case(organization_id, member_id, "nuova", "2026-01-10T09:00:00Z", "D1")
    _case(organization_id, member_id, "chiusa", "2026-02-10T09:00:00Z", "D2")
    damage_policy_service.save_policy(DamagePolicy(
        organization_id=organization_id,
        enabled=False,
        free_events_count=1,
    ))

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.policy_enabled is False
    assert state.total_attributed_cases == 2
    assert state.countable_cases == 2
    assert state.free_events_count == 1
    assert state.free_events_used == 0
    assert state.events_over_threshold == 0
    assert state.next_event_is_over_threshold is False


@pytest.mark.parametrize(
    ("free_events", "used", "over", "next_over"),
    [(0, 0, 3, True), (1, 1, 2, True), (2, 2, 1, True)],
)
def test_enabled_policy_applies_configured_free_events(
    free_events, used, over, next_over
):
    organization_id = f"organization-free-{free_events}"
    member_id = _member(organization_id, f"FREE-{free_events}")
    for index in range(3):
        _case(
            organization_id,
            member_id,
            "nuova",
            f"2026-0{index + 1}-10T09:00:00Z",
            f"F{free_events}{index}",
        )
    damage_policy_service.save_policy(DamagePolicy(
        organization_id=organization_id,
        enabled=True,
        free_events_count=free_events,
    ))

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.free_events_used == used
    assert state.events_over_threshold == over
    assert state.next_event_is_over_threshold is next_over


def test_all_time_counts_every_countable_attributed_case():
    organization_id = "organization-all-time"
    member_id = _member(organization_id, "ALL-TIME")
    _case(organization_id, member_id, "nuova", "2020-01-01T09:00:00Z", "A1")
    _case(organization_id, member_id, "chiusa", "2026-08-08T09:00:00Z", "A2")

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.countable_cases == 2
    assert state.period_start is None
    assert state.period_end is None


def test_calendar_year_uses_reference_year():
    organization_id = "organization-year"
    member_id = _member(organization_id, "YEAR")
    _case(organization_id, member_id, "nuova", "2025-12-31T09:00:00Z", "Y1")
    _case(organization_id, member_id, "nuova", "2026-01-01T09:00:00Z", "Y2")
    _case(organization_id, member_id, "chiusa", "2026-12-31T09:00:00Z", "Y3")
    damage_policy_service.save_policy(DamagePolicy(
        organization_id=organization_id,
        counting_period=DamageCountingPeriod.CALENDAR_YEAR,
    ))

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.total_attributed_cases == 3
    assert state.countable_cases == 2
    assert state.period_start == date(2026, 1, 1)
    assert state.period_end == date(2026, 12, 31)


def test_rolling_twelve_months_uses_inclusive_reference_window():
    organization_id = "organization-rolling"
    member_id = _member(organization_id, "ROLLING")
    _case(organization_id, member_id, "nuova", "2025-08-07T09:00:00Z", "R1")
    _case(organization_id, member_id, "nuova", "2025-08-08T09:00:00Z", "R2")
    _case(organization_id, member_id, "chiusa", "2026-08-08T09:00:00Z", "R3")
    _case(organization_id, member_id, "nuova", "2026-08-09T09:00:00Z", "R4")
    damage_policy_service.save_policy(DamagePolicy(
        organization_id=organization_id,
        counting_period=DamageCountingPeriod.ROLLING_12_MONTHS,
    ))

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.countable_cases == 2
    assert state.period_start == date(2025, 8, 8)
    assert state.period_end == REFERENCE_DATE


def test_countable_event_order_is_occurred_at_then_case_id():
    cases = [
        {"id": 9, "occurred_at": "2026-01-02T10:00:00Z", "status": "nuova", "driver_workforce_member_id": 1},
        {"id": 8, "occurred_at": "2026-01-02T10:00:00Z", "status": "chiusa", "driver_workforce_member_id": 1},
        {"id": 10, "occurred_at": "2026-01-01T10:00:00Z", "status": "nuova", "driver_workforce_member_id": 1},
    ]

    ordered = damage_counter_service.countable_cases_for_period(
        cases, DamageCountingPeriod.ALL_TIME, REFERENCE_DATE
    )

    assert [item["id"] for item in ordered] == [10, 8, 9]
    classified = damage_counter_service.classify_countable_events(
        ordered,
        policy_enabled=True,
        free_events_count=1,
    )
    assert [(item["id"], free, over) for item, free, over in classified] == [
        (10, True, False),
        (8, False, True),
        (9, False, True),
    ]


def test_driver_without_cases_has_zero_state():
    organization_id = "organization-empty"
    member_id = _member(organization_id, "EMPTY")

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.total_attributed_cases == 0
    assert state.countable_cases == 0


def test_mixed_cases_distinguish_attributed_from_countable():
    organization_id = "organization-mixed"
    member_id = _member(organization_id, "MIXED")
    _case(organization_id, member_id, "nuova", "2026-01-01T09:00:00Z", "M1")
    _case(organization_id, member_id, "annullata", "2026-01-02T09:00:00Z", "M2")
    _case(organization_id, None, "chiusa", "2026-01-03T09:00:00Z", "M3")

    state = damage_counter_service.driver_policy_state(
        organization_id, member_id, REFERENCE_DATE
    )

    assert state.total_attributed_cases == 2
    assert state.countable_cases == 1


def test_organization_isolation_rejects_foreign_driver_and_cases():
    member_a = _member("organization-isolated-a", "ISO-A")
    member_b = _member("organization-isolated-b", "ISO-B")
    _case("organization-isolated-a", member_a, "nuova", NOW, "I1")
    _case("organization-isolated-b", member_b, "nuova", NOW, "I2")

    state_a = damage_counter_service.driver_policy_state(
        "organization-isolated-a", member_a, REFERENCE_DATE
    )

    assert state_a.total_attributed_cases == 1
    with pytest.raises(damage_counter_service.DamagePolicyDriverNotFound):
        damage_counter_service.driver_policy_state(
            "organization-isolated-a", member_b, REFERENCE_DATE
        )


def test_no_policy_counter_is_persisted_in_workforce_or_damage_cases():
    with db_session() as conn:
        workforce_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(workforce_members)")
        }
        damage_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(damage_cases)")
        }

    forbidden = {
        "damage_count",
        "countable_cases",
        "free_events_used",
        "events_over_threshold",
    }
    assert forbidden.isdisjoint(workforce_columns)
    assert forbidden.isdisjoint(damage_columns)

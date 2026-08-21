import json
import sqlite3
from inspect import getsource

import pytest

from app.core.database import db_session
from app.repositories.weekly_workforce_proposal_schema import init_schema
from app.repositories import weekly_workforce_proposal_schema as schema_module


TABLES = (
    "weekly_planning_input_snapshots",
    "weekly_workforce_proposals",
    "weekly_workforce_proposal_assignments",
    "weekly_workforce_proposal_gaps",
    "weekly_workforce_proposal_explainability",
    "weekly_workforce_proposal_events",
)


@pytest.fixture(autouse=True)
def reset_weekly_proposal_schema() -> None:
    init_schema()
    with db_session() as conn:
        for table in reversed(TABLES):
            conn.execute(f"DELETE FROM {table}")


def _insert_snapshot(
    *,
    organization_id: str = "organization-one",
    snapshot_id: str = "snapshot-one",
    fingerprint: str = "fingerprint-one",
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO weekly_planning_input_snapshots (
                organization_id, snapshot_id, period_start, period_end,
                operational_unit_identifier, operational_unit_name,
                policy_set_identifier, policy_set_version, fingerprint,
                created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                snapshot_id,
                "2026-08-24",
                "2026-08-30",
                "unit-north",
                "North depot",
                "policy-set",
                "1",
                fingerprint,
                "2026-08-21T10:00:00+00:00",
                json.dumps({"snapshot_id": snapshot_id}),
            ),
        )


def _insert_proposal(
    *,
    organization_id: str = "organization-one",
    proposal_id: str = "proposal-one",
    version: int = 1,
    snapshot_id: str = "snapshot-one",
    fingerprint: str = "fingerprint-one",
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO weekly_workforce_proposals (
                organization_id, proposal_id, version, period_start,
                period_end, operational_unit_identifier,
                operational_unit_name, input_snapshot_id,
                input_fingerprint, policy_set_identifier,
                policy_set_version, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                proposal_id,
                version,
                "2026-08-24",
                "2026-08-30",
                "unit-north",
                "North depot",
                snapshot_id,
                fingerprint,
                "policy-set",
                "1",
                "GENERATED",
                "2026-08-21T10:00:00+00:00",
            ),
        )


def _seed_revision(
    *,
    organization_id: str = "organization-one",
    proposal_id: str = "proposal-one",
    version: int = 1,
) -> None:
    snapshot_id = f"snapshot-{organization_id}-{version}"
    fingerprint = f"fingerprint-{organization_id}-{version}"
    _insert_snapshot(
        organization_id=organization_id,
        snapshot_id=snapshot_id,
        fingerprint=fingerprint,
    )
    _insert_proposal(
        organization_id=organization_id,
        proposal_id=proposal_id,
        version=version,
        snapshot_id=snapshot_id,
        fingerprint=fingerprint,
    )


def _insert_assignment(
    *,
    assignment_id: str = "assignment-one",
    version: int = 1,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO weekly_workforce_proposal_assignments (
                organization_id, proposal_id, proposal_version,
                assignment_id, workforce_member_id, operational_date,
                operational_unit_identifier, operational_unit_name,
                time_window_identifier, starts_at, ends_at,
                capability_or_workload, shift_identifier, origin, status,
                deterministic_priority, locked, reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "organization-one",
                "proposal-one",
                version,
                assignment_id,
                "member-one",
                "2026-08-24",
                "unit-north",
                "North depot",
                "morning-window",
                "08:00",
                "16:00",
                "parcel-delivery",
                None,
                "AUTOMATIC",
                "PROPOSED",
                0,
                0,
                json.dumps([{"code": "ranked", "message": "Rank one"}]),
            ),
        )


def test_bootstrap_creates_all_tables_and_is_idempotent() -> None:
    init_schema()
    init_schema()

    with db_session() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    assert set(TABLES).issubset({row["name"] for row in rows})


def test_organization_is_not_null_and_has_no_default_in_every_table() -> None:
    with db_session() as conn:
        for table in TABLES:
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            organization = next(
                column for column in columns if column["name"] == "organization_id"
            )
            assert organization["notnull"] == 1
            assert organization["dflt_value"] is None


def test_proposal_revision_identity_is_unique_but_versioned_and_tenant_scoped() -> None:
    _seed_revision(version=1)
    _seed_revision(version=2)
    _seed_revision(organization_id="organization-two", version=1)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_proposal(
            organization_id="organization-one",
            proposal_id="proposal-one",
            version=1,
            snapshot_id="snapshot-organization-one-1",
            fingerprint="fingerprint-organization-one-1",
        )


def test_assignment_identity_is_unique_only_inside_one_revision() -> None:
    _seed_revision(version=1)
    _seed_revision(version=2)
    _insert_assignment(version=1)
    _insert_assignment(version=2)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_assignment(version=1)


def test_gap_demand_trace_is_unique_inside_one_revision() -> None:
    _seed_revision()
    statement = """
        INSERT INTO weekly_workforce_proposal_gaps (
            organization_id, proposal_id, proposal_version, demand_trace_id,
            operational_date, operational_unit_identifier,
            operational_unit_name, time_window_identifier,
            capability_or_workload, required_quantity, proposed_quantity,
            gap_quantity, reasons_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        "organization-one", "proposal-one", 1, "demand-trace-one",
        "2026-08-24", "unit-north", None, "morning-window",
        "parcel-delivery", 3, 2, 1, json.dumps({"code": "shortage"}),
    )
    with db_session() as conn:
        conn.execute(statement, values)
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(statement, values)


def test_explainability_ordinal_is_unique_per_trace_and_artifact() -> None:
    _seed_revision()
    statement = """
        INSERT INTO weekly_workforce_proposal_explainability (
            organization_id, proposal_id, proposal_version, demand_trace_id,
            artifact_type, ordinal, workforce_member_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        "organization-one", "proposal-one", 1, "demand-trace-one",
        "ELIGIBILITY", 0, "member-one", json.dumps({"eligible": True}),
    )
    with db_session() as conn:
        conn.execute(statement, values)
        conn.execute(
            statement,
            (
                "organization-one", "proposal-one", 1, "demand-trace-one",
                "ELIGIBILITY", 1, "member-two", json.dumps({"eligible": True}),
            ),
        )
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(statement, values)


def test_snapshot_identity_is_unique_per_organization_and_json_is_text() -> None:
    _insert_snapshot()
    _insert_snapshot(organization_id="organization-two")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_snapshot()

    with db_session() as conn:
        row = conn.execute(
            """SELECT payload_json FROM weekly_planning_input_snapshots
               WHERE organization_id = ? AND snapshot_id = ?""",
            ("organization-one", "snapshot-one"),
        ).fetchone()

    assert isinstance(row["payload_json"], str)
    assert json.loads(row["payload_json"]) == {"snapshot_id": "snapshot-one"}


def test_proposal_snapshot_reference_requires_matching_fingerprint() -> None:
    _insert_snapshot()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_proposal(fingerprint="different-fingerprint")


def test_failed_transaction_rolls_back_all_rows() -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            values = (
                "rollback-organization", "rollback-snapshot",
                "2026-08-24", "2026-08-30", "unit-north", None,
                "policy-set", "1", "rollback-fingerprint",
                "2026-08-21T10:00:00+00:00", "{}",
            )
            statement = """
                INSERT INTO weekly_planning_input_snapshots (
                    organization_id, snapshot_id, period_start, period_end,
                    operational_unit_identifier, operational_unit_name,
                    policy_set_identifier, policy_set_version, fingerprint,
                    created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            conn.execute(statement, values)
            conn.execute(statement, values)

    with db_session() as conn:
        count = conn.execute(
            """SELECT COUNT(*) AS total
               FROM weekly_planning_input_snapshots
               WHERE organization_id = ?""",
            ("rollback-organization",),
        ).fetchone()
    assert count["total"] == 0


def test_schema_has_no_current_default_tenant_or_legacy_published_relation() -> None:
    source = getsource(schema_module).casefold()

    assert "is_current" not in source
    assert " default 'default'" not in source
    assert "driver_shift_planning_published_rows" not in source
    assert "jsonb" not in source
    assert "drop table" not in source


def test_all_child_foreign_keys_target_dedicated_proposal_revision() -> None:
    child_tables = TABLES[2:]
    with db_session() as conn:
        for table in child_tables:
            foreign_keys = conn.execute(
                f"PRAGMA foreign_key_list({table})"
            ).fetchall()
            targets = {row["table"] for row in foreign_keys}
            assert targets == {"weekly_workforce_proposals"}


def test_main_registers_weekly_proposal_schema_bootstrap() -> None:
    from app import main as app_main

    source = getsource(app_main)
    assert "init_weekly_workforce_proposal_schema()" in source

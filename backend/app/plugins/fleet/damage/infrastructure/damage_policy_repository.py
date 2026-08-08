from app.core.database import db_session
from app.plugins.fleet.damage.domain.damage_policy import (
    DamageCountingPeriod,
    DamagePolicy,
)
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS damage_policies (
                organization_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                free_events_count INTEGER NOT NULL DEFAULT 0,
                counting_period TEXT NOT NULL DEFAULT 'all_time',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (enabled IN (0, 1)),
                CHECK (free_events_count >= 0),
                CHECK (counting_period IN (
                    'all_time', 'calendar_year', 'rolling_12_months'
                ))
            )
            """
        )


def _from_row(row) -> DamagePolicy | None:
    if row is None:
        return None
    return DamagePolicy(
        organization_id=str(row["organization_id"]),
        enabled=bool(row["enabled"]),
        free_events_count=int(row["free_events_count"]),
        counting_period=DamageCountingPeriod(str(row["counting_period"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_policy(organization_id: str) -> DamagePolicy | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM damage_policies WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
    return _from_row(row)


def save_policy(policy: DamagePolicy) -> DamagePolicy:
    now = utc_now_iso()
    created_at = policy.created_at or now
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO damage_policies (
                organization_id, enabled, free_events_count, counting_period,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(organization_id) DO UPDATE SET
                enabled = excluded.enabled,
                free_events_count = excluded.free_events_count,
                counting_period = excluded.counting_period,
                updated_at = excluded.updated_at
            """,
            (
                policy.organization_id,
                int(policy.enabled),
                policy.free_events_count,
                policy.counting_period.value,
                created_at,
                now,
            ),
        )
    saved = get_policy(policy.organization_id)
    assert saved is not None
    return saved


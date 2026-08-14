import uuid
from datetime import UTC, datetime

from app.auth.maintenance_domain import MaintenanceTokenStatus
from app.core.database import db_session


MAX_ACTIVE_TOKENS_PER_ORGANIZATION = 5


class MaintenanceTokenLimitError(RuntimeError):
    pass


def _audit(
    conn,
    *,
    organization_id: str,
    user_id: str,
    action: str,
    target: str,
    status_code: int,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_events (
            id, organization_id, user_id, action, target, status_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()), organization_id, user_id, action, target,
            status_code, created_at,
        ),
    )


def _expire_due(conn, organization_id: str, now: str) -> None:
    rows = conn.execute(
        """
        SELECT id, created_by, scope
        FROM maintenance_tokens
        WHERE organization_id = ? AND status = ? AND expires_at <= ?
        """,
        (organization_id, MaintenanceTokenStatus.ACTIVE.value, now),
    ).fetchall()
    if not rows:
        return
    conn.execute(
        """
        UPDATE maintenance_tokens SET status = ?
        WHERE organization_id = ? AND status = ? AND expires_at <= ?
        """,
        (
            MaintenanceTokenStatus.EXPIRED.value,
            organization_id,
            MaintenanceTokenStatus.ACTIVE.value,
            now,
        ),
    )
    for row in rows:
        _audit(
            conn,
            organization_id=organization_id,
            user_id=row["created_by"],
            action="maintenance_token_expired",
            target=f"maintenance-token:{row['id']}|scope:{row['scope']}",
            status_code=401,
            created_at=now,
        )


def create(
    *,
    token_id: str,
    organization_id: str,
    token_hash: str,
    scope: str,
    created_by: str,
    created_at: str,
    expires_at: str,
) -> None:
    with db_session() as conn:
        _expire_due(conn, organization_id, created_at)
        active = conn.execute(
            """
            SELECT COUNT(*) AS total FROM maintenance_tokens
            WHERE organization_id = ? AND status = ? AND expires_at > ?
            """,
            (
                organization_id,
                MaintenanceTokenStatus.ACTIVE.value,
                created_at,
            ),
        ).fetchone()
        if int(active["total"]) >= MAX_ACTIVE_TOKENS_PER_ORGANIZATION:
            raise MaintenanceTokenLimitError(
                "Sono gia presenti cinque token di manutenzione attivi."
            )
        conn.execute(
            """
            INSERT INTO maintenance_tokens (
                id, organization_id, token_hash, scope, created_by, created_at,
                expires_at, revoked_at, used_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                token_id, organization_id, token_hash, scope, created_by,
                created_at, expires_at, MaintenanceTokenStatus.ACTIVE.value,
            ),
        )
        _audit(
            conn,
            organization_id=organization_id,
            user_id=created_by,
            action="maintenance_token_created",
            target=f"maintenance-token:{token_id}|scope:{scope}",
            status_code=201,
            created_at=created_at,
        )


def find_by_hash(token_hash: str):
    with db_session() as conn:
        return conn.execute(
            """
            SELECT id, organization_id, scope, created_by, expires_at,
                   revoked_at, used_at, status
            FROM maintenance_tokens WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()


def expire(token_id: str, organization_id: str, now: str) -> None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, created_by, scope, status FROM maintenance_tokens
            WHERE id = ? AND organization_id = ?
            """,
            (token_id, organization_id),
        ).fetchone()
        if not row or row["status"] != MaintenanceTokenStatus.ACTIVE.value:
            return
        conn.execute(
            "UPDATE maintenance_tokens SET status = ? WHERE id = ? AND organization_id = ?",
            (MaintenanceTokenStatus.EXPIRED.value, token_id, organization_id),
        )
        _audit(
            conn,
            organization_id=organization_id,
            user_id=row["created_by"],
            action="maintenance_token_expired",
            target=f"maintenance-token:{token_id}|scope:{row['scope']}",
            status_code=401,
            created_at=now,
        )


def record_usage(
    *,
    token_id: str,
    organization_id: str,
    created_by: str,
    scope: str,
    endpoint: str,
    status_code: int,
    used_at: str,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE maintenance_tokens SET used_at = ?
            WHERE id = ? AND organization_id = ? AND status = ?
            """,
            (
                used_at, token_id, organization_id,
                MaintenanceTokenStatus.ACTIVE.value,
            ),
        )
        _audit(
            conn,
            organization_id=organization_id,
            user_id=created_by,
            action="maintenance_token_used",
            target=f"maintenance-token:{token_id}|scope:{scope}|endpoint:{endpoint}",
            status_code=status_code,
            created_at=used_at,
        )


def revoke(
    *, token_id: str, organization_id: str, revoked_by: str, revoked_at: str
) -> bool:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, scope, status FROM maintenance_tokens
            WHERE id = ? AND organization_id = ?
            """,
            (token_id, organization_id),
        ).fetchone()
        if not row:
            return False
        if row["status"] == MaintenanceTokenStatus.ACTIVE.value:
            conn.execute(
                """
                UPDATE maintenance_tokens
                SET revoked_at = ?, status = ?
                WHERE id = ? AND organization_id = ?
                """,
                (
                    revoked_at, MaintenanceTokenStatus.REVOKED.value,
                    token_id, organization_id,
                ),
            )
        _audit(
            conn,
            organization_id=organization_id,
            user_id=revoked_by,
            action="maintenance_token_revoked",
            target=f"maintenance-token:{token_id}|scope:{row['scope']}",
            status_code=204,
            created_at=revoked_at,
        )
    return True


from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def _dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def portal_context(token_hash: str) -> dict | None:
    now = utc_now_iso()
    with db_session() as conn:
        row = conn.execute(
            """SELECT p.id portal_id, p.organization_id, p.distribution_id,
                      p.token_generation portal_generation, p.expires_at portal_expires_at,
                      p.status portal_status, d.status distribution_status,
                      d.period_start, d.period_end
               FROM driver_shift_distribution_portals p
               JOIN driver_shift_distributions d
                 ON d.id=p.distribution_id AND d.organization_id=p.organization_id
               WHERE p.token_hash=? AND p.status='ACTIVE' AND p.expires_at >= ?
                 AND d.status IN ('READY', 'DISTRIBUTED')""",
            (token_hash, now),
        ).fetchone()
    return _dict(row) if row is not None else None


def credential_for_portal(
    organization_id: str,
    distribution_id: int,
    access_code_hash: str,
) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """SELECT c.id credential_id, c.organization_id, c.workforce_member_id,
                      c.credential_status, c.pin_hash, c.generation credential_generation,
                      m.display_name, r.id recipient_id, r.access_status,
                      r.access_revoked_at
               FROM driver_shift_driver_credentials c
               JOIN workforce_members m
                 ON m.id=c.workforce_member_id AND m.organization_id=c.organization_id
               JOIN driver_shift_distribution_recipients r
                 ON r.organization_id=c.organization_id
                AND r.workforce_member_id=c.workforce_member_id
                AND r.distribution_id=?
               WHERE c.organization_id=? AND c.access_code_hash=?""",
            (distribution_id, organization_id, access_code_hash),
        ).fetchone()
    return _dict(row) if row is not None else None


def create_session(
    *,
    session_token_hash: str,
    organization_id: str,
    workforce_member_id: int,
    distribution_id: int,
    portal_id: int,
    portal_generation: int,
    credential_generation: int,
    expires_at: str,
    remember_device: bool,
) -> str:
    session_id = str(uuid4())
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO driver_shift_driver_sessions (
                   id, session_token_hash, organization_id, workforce_member_id,
                   distribution_id, portal_id, portal_generation,
                   credential_generation, created_at, expires_at, last_seen_at,
                   revoked_at, remember_device
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
            (
                session_id, session_token_hash, organization_id, workforce_member_id,
                distribution_id, portal_id, portal_generation, credential_generation,
                now, expires_at, now, int(remember_device),
            ),
        )
    return session_id


def session_view(session_token_hash: str) -> dict | None:
    now = utc_now_iso()
    with db_session() as conn:
        row = conn.execute(
            """SELECT s.id session_id, s.expires_at, s.organization_id,
                      m.display_name, d.period_start, d.period_end,
                      r.id recipient_id, r.access_status
               FROM driver_shift_driver_sessions s
               JOIN driver_shift_distribution_portals p
                 ON p.id=s.portal_id AND p.organization_id=s.organization_id
               JOIN driver_shift_distributions d
                 ON d.id=s.distribution_id AND d.organization_id=s.organization_id
               JOIN driver_shift_driver_credentials c
                 ON c.organization_id=s.organization_id
                AND c.workforce_member_id=s.workforce_member_id
               JOIN driver_shift_distribution_recipients r
                 ON r.organization_id=s.organization_id
                AND r.distribution_id=s.distribution_id
                AND r.workforce_member_id=s.workforce_member_id
               JOIN workforce_members m
                 ON m.id=s.workforce_member_id AND m.organization_id=s.organization_id
               WHERE s.session_token_hash=? AND s.revoked_at IS NULL
                 AND s.expires_at >= ?
                 AND p.status='ACTIVE' AND p.expires_at >= ?
                 AND p.token_generation=s.portal_generation
                 AND d.status IN ('READY', 'DISTRIBUTED')
                 AND c.credential_status='ACTIVE'
                 AND c.generation=s.credential_generation
                 AND r.access_revoked_at IS NULL""",
            (session_token_hash, now, now),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE driver_shift_driver_sessions SET last_seen_at=? WHERE id=?",
            (now, row["session_id"]),
        )
        conn.execute(
            """UPDATE driver_shift_distribution_recipients
               SET first_opened_at=COALESCE(first_opened_at, ?), last_opened_at=?,
                   access_status=CASE
                       WHEN acknowledged_at IS NULL THEN 'OPENED'
                       ELSE 'ACKNOWLEDGED'
                   END,
                   updated_at=?
               WHERE id=?""",
            (now, now, now, row["recipient_id"]),
        )
        refreshed = conn.execute(
            "SELECT access_status FROM driver_shift_distribution_recipients WHERE id=?",
            (row["recipient_id"],),
        ).fetchone()
        result = _dict(row)
        result["access_status"] = str(refreshed["access_status"])
        return result


def revoke_session(session_token_hash: str) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """UPDATE driver_shift_driver_sessions
               SET revoked_at=COALESCE(revoked_at, ?), last_seen_at=?
               WHERE session_token_hash=?""",
            (now, now, session_token_hash),
        )


def _cutoff(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def failed_attempt_counts(
    portal_id: int,
    access_code_fingerprint: str,
    ip_fingerprint: str,
    *,
    window_minutes: int,
) -> tuple[int, int]:
    cutoff = _cutoff(window_minutes)
    with db_session() as conn:
        code_row = conn.execute(
            """SELECT COUNT(*) total FROM driver_shift_login_attempts
               WHERE portal_id=? AND access_code_fingerprint=?
                 AND succeeded=0 AND attempted_at >= ?""",
            (portal_id, access_code_fingerprint, cutoff),
        ).fetchone()
        ip_row = conn.execute(
            """SELECT COUNT(*) total FROM driver_shift_login_attempts
               WHERE portal_id=? AND ip_fingerprint=?
                 AND succeeded=0 AND attempted_at >= ?""",
            (portal_id, ip_fingerprint, cutoff),
        ).fetchone()
    return int(code_row["total"]), int(ip_row["total"])


def record_login_attempt(
    *,
    organization_id: str,
    portal_id: int,
    access_code_fingerprint: str,
    ip_fingerprint: str,
    succeeded: bool,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        if succeeded:
            conn.execute(
                """DELETE FROM driver_shift_login_attempts
                   WHERE portal_id=? AND succeeded=0
                     AND (access_code_fingerprint=? OR ip_fingerprint=?)""",
                (portal_id, access_code_fingerprint, ip_fingerprint),
            )
            return
        conn.execute(
            """INSERT INTO driver_shift_login_attempts (
                   id, organization_id, portal_id, access_code_fingerprint, ip_fingerprint,
                   attempted_at, succeeded
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()), organization_id, portal_id, access_code_fingerprint,
                ip_fingerprint, now, int(succeeded),
            ),
        )
        conn.execute(
            "DELETE FROM driver_shift_login_attempts WHERE attempted_at < ?",
            (_cutoff(1440),),
        )

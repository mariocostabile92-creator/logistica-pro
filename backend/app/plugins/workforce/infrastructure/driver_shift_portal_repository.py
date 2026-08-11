import json

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_portal import (
    DriverShiftPortalInvalidError,
    DriverShiftPortalNotFoundError,
)
from app.utils.date_utils import utc_now_iso


def _dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def _audit(conn, organization_id: str, portal_id: int, actor: str,
           reason: str, payload: dict[str, object]) -> None:
    conn.execute(
        """INSERT INTO workforce_changes (
               entity_type, entity_id, actor, timestamp, before_value,
               after_value, reason, source, organization_id
           ) VALUES ('driver_shift_distribution_portal', ?, ?, ?, NULL, ?, ?,
                     'driver_shift_distribution_portal', ?)""",
        (str(portal_id), actor, utc_now_iso(),
         json.dumps(payload, ensure_ascii=False), reason, organization_id),
    )


def _distribution(conn, organization_id: str, distribution_id: int):
    row = conn.execute(
        """SELECT * FROM driver_shift_distributions
           WHERE id=? AND organization_id=?""",
        (distribution_id, organization_id),
    ).fetchone()
    if row is None:
        raise DriverShiftPortalNotFoundError("Distribuzione turni non trovata.")
    return row


def distribution_period_end(organization_id: str, distribution_id: int) -> str:
    with db_session() as conn:
        distribution = _distribution(conn, organization_id, distribution_id)
        if distribution["status"] == "SUPERSEDED":
            raise DriverShiftPortalInvalidError(
                "Una distribuzione superata non può avere un portale attivo."
            )
        return str(distribution["period_end"])


def _sync_lifecycle(conn, portal, distribution, now: str):
    if portal is None:
        return None
    if portal["status"] == "ACTIVE" and distribution["status"] == "SUPERSEDED":
        conn.execute(
            """UPDATE driver_shift_distribution_portals
               SET status='REVOKED', revoked_at=COALESCE(revoked_at, ?), updated_at=?
               WHERE id=?""",
            (now, now, portal["id"]),
        )
    elif portal["status"] == "ACTIVE" and str(portal["expires_at"]) < now:
        conn.execute(
            """UPDATE driver_shift_distribution_portals
               SET status='EXPIRED', updated_at=? WHERE id=?""",
            (now, portal["id"]),
        )
    return conn.execute(
        "SELECT * FROM driver_shift_distribution_portals WHERE id=?",
        (portal["id"],),
    ).fetchone()


def portal_for_distribution(organization_id: str, distribution_id: int) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        distribution = _distribution(conn, organization_id, distribution_id)
        portal = conn.execute(
            """SELECT * FROM driver_shift_distribution_portals
               WHERE organization_id=? AND distribution_id=?""",
            (organization_id, distribution_id),
        ).fetchone()
        portal = _sync_lifecycle(conn, portal, distribution, now)
        if portal is None:
            raise DriverShiftPortalNotFoundError("Portale condiviso non preparato.")
        return _dict(portal)


def prepare_portal(
    organization_id: str,
    distribution_id: int,
    public_id: str,
    token_hash: str,
    expires_at: str,
    actor: str,
) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        distribution = _distribution(conn, organization_id, distribution_id)
        if distribution["status"] == "SUPERSEDED" or expires_at < now:
            raise DriverShiftPortalInvalidError(
                "La distribuzione non è più disponibile per un portale condiviso."
            )
        existing = conn.execute(
            """SELECT * FROM driver_shift_distribution_portals
               WHERE organization_id=? AND distribution_id=?""",
            (organization_id, distribution_id),
        ).fetchone()
        existing = _sync_lifecycle(conn, existing, distribution, now)
        if existing is not None:
            return _dict(existing)
        cursor = conn.execute(
            """INSERT INTO driver_shift_distribution_portals (
                   organization_id, distribution_id, public_id, token_hash,
                   token_generation, status, expires_at, created_at, created_by,
                   revoked_at, updated_at
               ) VALUES (?, ?, ?, ?, 1, 'ACTIVE', ?, ?, ?, NULL, ?)""",
            (organization_id, distribution_id, public_id, token_hash,
             expires_at, now, actor, now),
        )
        portal_id = int(cursor.lastrowid)
        _audit(conn, organization_id, portal_id, actor,
               "driver_shift_portal_prepared", {"distribution_id": distribution_id})
        row = conn.execute(
            "SELECT * FROM driver_shift_distribution_portals WHERE id=?",
            (portal_id,),
        ).fetchone()
        assert row is not None
        return _dict(row)


def revoke_portal(organization_id: str, distribution_id: int, actor: str) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        _distribution(conn, organization_id, distribution_id)
        changed = conn.execute(
            """UPDATE driver_shift_distribution_portals
               SET status='REVOKED', revoked_at=COALESCE(revoked_at, ?), updated_at=?
               WHERE organization_id=? AND distribution_id=?""",
            (now, now, organization_id, distribution_id),
        )
        if changed.rowcount == 0:
            raise DriverShiftPortalNotFoundError("Portale condiviso non preparato.")
        row = conn.execute(
            """SELECT * FROM driver_shift_distribution_portals
               WHERE organization_id=? AND distribution_id=?""",
            (organization_id, distribution_id),
        ).fetchone()
        assert row is not None
        _audit(conn, organization_id, int(row["id"]), actor,
               "driver_shift_portal_revoked", {"distribution_id": distribution_id})
        return _dict(row)


def regenerate_portal(
    organization_id: str,
    distribution_id: int,
    public_id: str,
    token_hash: str,
    expires_at: str,
    actor: str,
) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        distribution = _distribution(conn, organization_id, distribution_id)
        if distribution["status"] == "SUPERSEDED" or expires_at < now:
            raise DriverShiftPortalInvalidError(
                "La distribuzione non è più disponibile per un portale condiviso."
            )
        row = conn.execute(
            """SELECT * FROM driver_shift_distribution_portals
               WHERE organization_id=? AND distribution_id=?""",
            (organization_id, distribution_id),
        ).fetchone()
        if row is None:
            raise DriverShiftPortalNotFoundError("Portale condiviso non preparato.")
        generation = int(row["token_generation"]) + 1
        conn.execute(
            """UPDATE driver_shift_distribution_portals
               SET public_id=?, token_hash=?, token_generation=?, status='ACTIVE',
                   expires_at=?, revoked_at=NULL, updated_at=?
               WHERE id=?""",
            (public_id, token_hash, generation, expires_at, now, row["id"]),
        )
        _audit(conn, organization_id, int(row["id"]), actor,
               "driver_shift_portal_regenerated", {
                   "distribution_id": distribution_id, "generation": generation,
               })
        refreshed = conn.execute(
            "SELECT * FROM driver_shift_distribution_portals WHERE id=?",
            (row["id"],),
        ).fetchone()
        assert refreshed is not None
        return _dict(refreshed)


def validate_token(token_hash: str) -> bool:
    now = utc_now_iso()
    with db_session() as conn:
        row = conn.execute(
            """SELECT p.id
               FROM driver_shift_distribution_portals p
               JOIN driver_shift_distributions d
                 ON d.id=p.distribution_id AND d.organization_id=p.organization_id
               WHERE p.token_hash=? AND p.status='ACTIVE'
                 AND p.expires_at >= ?
                 AND d.status IN ('READY', 'DISTRIBUTED')""",
            (token_hash, now),
        ).fetchone()
    if row is None:
        raise DriverShiftPortalNotFoundError("Accesso turni non disponibile.")
    return True

import json
from collections.abc import Sequence

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_credentials import (
    DriverShiftCredentialError,
    DriverShiftCredentialNotFoundError,
)
from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionNotFoundError,
)
from app.utils.date_utils import utc_now_iso


def _dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def _audit_rows(conn, organization_id: str, actor: str, reason: str,
                rows: Sequence[dict[str, object]]) -> None:
    now = utc_now_iso()
    conn.executemany(
        """INSERT INTO workforce_changes (
               entity_type, entity_id, actor, timestamp, before_value,
               after_value, reason, source, organization_id
           ) VALUES ('driver_shift_driver_credential', ?, ?, ?, NULL, ?, ?,
                     'driver_shift_driver_credential', ?)""",
        [
            (
                str(row["workforce_member_id"]), actor, now,
                json.dumps({
                    "credential_status": row["credential_status"],
                    "generation": row["generation"],
                }, ensure_ascii=False),
                reason, organization_id,
            )
            for row in rows
        ],
    )


def distribution_recipients(organization_id: str, distribution_id: int,
                            *, require_current: bool = False) -> list[dict]:
    with db_session() as conn:
        distribution = conn.execute(
            """SELECT status FROM driver_shift_distributions
               WHERE id=? AND organization_id=?""",
            (distribution_id, organization_id),
        ).fetchone()
        if distribution is None:
            raise DriverShiftDistributionNotFoundError("Distribuzione turni non trovata.")
        if require_current and distribution["status"] == "SUPERSEDED":
            raise DriverShiftCredentialError(
                "Una distribuzione superata non può preparare credenziali."
            )
        rows = conn.execute(
            """SELECT r.workforce_member_id, m.display_name,
                      c.credential_status, c.generation
               FROM driver_shift_distribution_recipients r
               JOIN workforce_members m
                 ON m.id=r.workforce_member_id AND m.organization_id=r.organization_id
               LEFT JOIN driver_shift_driver_credentials c
                 ON c.organization_id=r.organization_id
                AND c.workforce_member_id=r.workforce_member_id
               WHERE r.organization_id=? AND r.distribution_id=?
               ORDER BY m.display_name, r.workforce_member_id""",
            (organization_id, distribution_id),
        ).fetchall()
    return [_dict(row) for row in rows]


def access_code_hashes() -> set[str]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT access_code_hash FROM driver_shift_driver_credentials"
        ).fetchall()
    return {str(row["access_code_hash"]) for row in rows}


def create_credentials(organization_id: str, distribution_id: int,
                       items: Sequence[dict[str, object]], actor: str) -> None:
    if not items:
        return
    now = utc_now_iso()
    member_ids = [int(item["workforce_member_id"]) for item in items]
    placeholders = ",".join("?" for _ in member_ids)
    with db_session() as conn:
        distribution = conn.execute(
            """SELECT status FROM driver_shift_distributions
               WHERE id=? AND organization_id=?""",
            (distribution_id, organization_id),
        ).fetchone()
        if distribution is None:
            raise DriverShiftDistributionNotFoundError("Distribuzione turni non trovata.")
        if distribution["status"] == "SUPERSEDED":
            raise DriverShiftCredentialError(
                "Una distribuzione superata non può preparare credenziali."
            )
        recipients = conn.execute(
            f"""SELECT workforce_member_id
                FROM driver_shift_distribution_recipients
                WHERE organization_id=? AND distribution_id=?
                  AND workforce_member_id IN ({placeholders})""",
            (organization_id, distribution_id, *member_ids),
        ).fetchall()
        if {int(row["workforce_member_id"]) for row in recipients} != set(member_ids):
            raise DriverShiftCredentialError(
                "Una o più credenziali non appartengono ai destinatari richiesti."
            )
        conn.executemany(
            """INSERT INTO driver_shift_driver_credentials (
                   organization_id, workforce_member_id, credential_status,
                   access_code_hash, pin_hash, generation, created_at, updated_at,
                   reset_at, revoked_at
               ) VALUES (?, ?, 'ACTIVE', ?, ?, 1, ?, ?, NULL, NULL)""",
            [
                (
                    organization_id, item["workforce_member_id"],
                    item["access_code_hash"], item["pin_hash"], now, now,
                )
                for item in items
            ],
        )
        _audit_rows(conn, organization_id, actor, "driver_shift_credentials_created", [
            {
                "workforce_member_id": item["workforce_member_id"],
                "credential_status": "ACTIVE",
                "generation": 1,
            }
            for item in items
        ])


def credential_by_access_code(organization_id: str, access_code_hash: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """SELECT * FROM driver_shift_driver_credentials
               WHERE organization_id=? AND access_code_hash=?""",
            (organization_id, access_code_hash),
        ).fetchone()
    return _dict(row) if row is not None else None


def reset_credential(organization_id: str, workforce_member_id: int,
                     pin_hash: str, actor: str) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        current = conn.execute(
            """SELECT c.*, m.display_name
               FROM driver_shift_driver_credentials c
               JOIN workforce_members m
                 ON m.id=c.workforce_member_id AND m.organization_id=c.organization_id
               WHERE c.organization_id=? AND c.workforce_member_id=?""",
            (organization_id, workforce_member_id),
        ).fetchone()
        if current is None:
            raise DriverShiftCredentialNotFoundError("Credenziale driver non trovata.")
        if current["credential_status"] == "REVOKED":
            raise DriverShiftCredentialError(
                "Una credenziale revocata non può essere reimpostata."
            )
        generation = int(current["generation"]) + 1
        conn.execute(
            """UPDATE driver_shift_driver_credentials
               SET pin_hash=?, generation=?, credential_status='ACTIVE',
                   reset_at=?, updated_at=?
               WHERE organization_id=? AND workforce_member_id=?""",
            (pin_hash, generation, now, now, organization_id, workforce_member_id),
        )
        _audit_rows(conn, organization_id, actor, "driver_shift_credentials_reset", [{
            "workforce_member_id": workforce_member_id,
            "credential_status": "ACTIVE",
            "generation": generation,
        }])
        row = conn.execute(
            """SELECT c.*, m.display_name
               FROM driver_shift_driver_credentials c
               JOIN workforce_members m
                 ON m.id=c.workforce_member_id AND m.organization_id=c.organization_id
               WHERE c.organization_id=? AND c.workforce_member_id=?""",
            (organization_id, workforce_member_id),
        ).fetchone()
        assert row is not None
        return _dict(row)


def revoke_credential(organization_id: str, workforce_member_id: int,
                      actor: str) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        current = conn.execute(
            """SELECT c.*, m.display_name
               FROM driver_shift_driver_credentials c
               JOIN workforce_members m
                 ON m.id=c.workforce_member_id AND m.organization_id=c.organization_id
               WHERE c.organization_id=? AND c.workforce_member_id=?""",
            (organization_id, workforce_member_id),
        ).fetchone()
        if current is None:
            raise DriverShiftCredentialNotFoundError("Credenziale driver non trovata.")
        conn.execute(
            """UPDATE driver_shift_driver_credentials
               SET credential_status='REVOKED', revoked_at=COALESCE(revoked_at, ?),
                   updated_at=?
               WHERE organization_id=? AND workforce_member_id=?""",
            (now, now, organization_id, workforce_member_id),
        )
        generation = int(current["generation"])
        _audit_rows(conn, organization_id, actor, "driver_shift_credentials_revoked", [{
            "workforce_member_id": workforce_member_id,
            "credential_status": "REVOKED",
            "generation": generation,
        }])
        row = conn.execute(
            """SELECT c.*, m.display_name
               FROM driver_shift_driver_credentials c
               JOIN workforce_members m
                 ON m.id=c.workforce_member_id AND m.organization_id=c.organization_id
               WHERE c.organization_id=? AND c.workforce_member_id=?""",
            (organization_id, workforce_member_id),
        ).fetchone()
        assert row is not None
        return _dict(row)

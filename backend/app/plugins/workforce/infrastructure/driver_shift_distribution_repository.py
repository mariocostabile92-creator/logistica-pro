import json
from collections.abc import Sequence

from app.core.database import db_session
from app.plugins.workforce.domain.driver_shift_contact import contact_readiness
from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistribution,
    DriverShiftDistributionError,
    DriverShiftDistributionNotFoundError,
    DriverShiftDistributionReadModel,
    DriverShiftDistributionRecipient,
    DriverShiftDistributionSummary,
    DriverShiftPersonalAccessNotFoundError,
    PersonalDriverShift,
    PersonalDriverShiftView,
)
from app.utils.date_utils import utc_now_iso


def _distribution(row) -> DriverShiftDistribution:
    return DriverShiftDistribution.model_validate({key: row[key] for key in row.keys()})


def _audit(conn, organization_id: str, entity_id: str, actor: str, reason: str,
           payload: dict[str, object]) -> None:
    conn.execute(
        """INSERT INTO workforce_changes (
               entity_type, entity_id, actor, timestamp, before_value,
               after_value, reason, source, organization_id
           ) VALUES ('driver_shift_distribution', ?, ?, ?, NULL, ?, ?,
                     'driver_shift_distribution', ?)""",
        (entity_id, actor, utc_now_iso(), json.dumps(payload, ensure_ascii=False),
         reason, organization_id),
    )


def active_planning(organization_id: str, planning_id: int) -> dict:
    with db_session() as conn:
        planning = conn.execute(
            """SELECT * FROM driver_shift_plannings
               WHERE id=? AND organization_id=?""",
            (planning_id, organization_id),
        ).fetchone()
        if planning is None:
            raise DriverShiftDistributionNotFoundError("Planning turni non trovato.")
        if planning["status"] != "ACTIVE":
            raise DriverShiftDistributionError("La distribuzione richiede un planning ACTIVE.")
    return {key: planning[key] for key in planning.keys()}


def published_recipient_candidates(
    organization_id: str,
    planning: dict,
    period_start: str,
    period_end: str,
) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT pr.workforce_member_id, m.display_name, COUNT(pr.id) shift_days_count
               FROM driver_shift_planning_published_rows pr
               JOIN workforce_members m
                 ON m.id=pr.workforce_member_id
                AND m.organization_id=pr.organization_id
               WHERE pr.organization_id=? AND pr.driver_shift_planning_id=?
                 AND pr.planning_version=?
                 AND pr.operational_date BETWEEN ? AND ?
               GROUP BY pr.workforce_member_id, m.display_name
               ORDER BY m.display_name, pr.workforce_member_id""",
            (
                organization_id,
                planning["id"],
                planning["version"],
                period_start,
                period_end,
            ),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _read_model_conn(conn, organization_id: str, distribution_id: int) -> DriverShiftDistributionReadModel:
    distribution = conn.execute(
        "SELECT * FROM driver_shift_distributions WHERE id=? AND organization_id=?",
        (distribution_id, organization_id),
    ).fetchone()
    if distribution is None:
        raise DriverShiftDistributionNotFoundError("Distribuzione turni non trovata.")
    rows = conn.execute(
        """SELECT r.id, r.workforce_member_id, m.display_name, m.phone, m.email,
                  r.delivery_status, r.access_status, r.access_revoked_at, r.first_opened_at,
                  r.last_opened_at, r.acknowledged_at, COUNT(pr.id) shift_days_count
           FROM driver_shift_distribution_recipients r
           JOIN workforce_members m
             ON m.id=r.workforce_member_id AND m.organization_id=r.organization_id
           LEFT JOIN driver_shift_planning_published_rows pr
             ON pr.organization_id=r.organization_id
            AND pr.driver_shift_planning_id=?
            AND pr.planning_version=?
            AND pr.workforce_member_id=r.workforce_member_id
            AND pr.operational_date BETWEEN ? AND ?
           WHERE r.organization_id=? AND r.distribution_id=?
           GROUP BY r.id, r.workforce_member_id, m.display_name, m.phone, m.email,
                    r.delivery_status, r.access_status, r.access_revoked_at, r.first_opened_at,
                    r.last_opened_at, r.acknowledged_at
           ORDER BY m.display_name, r.id""",
        (
            distribution["driver_shift_planning_id"],
            distribution["planning_version"],
            distribution["period_start"],
            distribution["period_end"],
            organization_id,
            distribution_id,
        ),
    ).fetchall()
    recipients = []
    for row in rows:
        values = {key: row[key] for key in row.keys()}
        contact = contact_readiness(values.pop("phone", None), values.pop("email", None))
        values["readiness"] = contact.readiness
        values["available_channels"] = list(contact.available_channels)
        values["preferred_channel"] = contact.preferred_channel
        values["access_revoked"] = bool(values.pop("access_revoked_at", None))
        recipients.append(DriverShiftDistributionRecipient.model_validate(values))
    summary = DriverShiftDistributionSummary(
        recipients_total=len(recipients),
        ready=sum(item.delivery_status == "READY" and not item.access_revoked for item in recipients),
        pending=sum(item.delivery_status == "PENDING" for item in recipients),
        contact_ready=sum(item.readiness == "READY" for item in recipients),
        missing_contact=sum(item.readiness == "MISSING_CONTACT" for item in recipients),
        invalid_contact=sum(item.readiness == "INVALID_CONTACT" for item in recipients),
        excluded=sum(item.readiness == "EXCLUDED" for item in recipients),
        opened=sum(item.access_status in {"OPENED", "ACKNOWLEDGED"} for item in recipients),
        acknowledged=sum(item.access_status == "ACKNOWLEDGED" for item in recipients),
        not_opened=sum(item.access_status == "NOT_OPENED" and not item.access_revoked for item in recipients),
    )
    return DriverShiftDistributionReadModel(
        distribution=_distribution(distribution), summary=summary, recipients=recipients,
    )


def prepare_distribution(
    organization_id: str,
    planning: dict,
    period_start: str,
    period_end: str,
    recipients: Sequence[dict[str, object]],
    actor: str,
) -> DriverShiftDistributionReadModel:
    now = utc_now_iso()
    with db_session() as conn:
        current = conn.execute(
            "SELECT * FROM driver_shift_plannings WHERE id=? AND organization_id=?",
            (planning["id"], organization_id),
        ).fetchone()
        if current is None:
            raise DriverShiftDistributionNotFoundError("Planning turni non trovato.")
        if current["status"] != "ACTIVE" or int(current["version"]) != int(planning["version"]):
            raise DriverShiftDistributionError("Il planning non è più ACTIVE: ricarica la pagina.")
        existing = conn.execute(
            """SELECT id FROM driver_shift_distributions
               WHERE organization_id=? AND driver_shift_planning_id=?
                 AND planning_version=? AND period_start=? AND period_end=?""",
            (
                organization_id,
                planning["id"],
                planning["version"],
                period_start,
                period_end,
            ),
        ).fetchone()
        if existing is not None:
            return _read_model_conn(conn, organization_id, int(existing["id"]))
        if not recipients:
            raise DriverShiftDistributionError("Il planning pubblicato non contiene destinatari.")
        previous = conn.execute(
            """SELECT id FROM driver_shift_distributions
               WHERE organization_id=? AND period_start=? AND period_end=?
                 AND status <> 'SUPERSEDED'""",
            (organization_id, period_start, period_end),
        ).fetchall()
        previous_ids = [int(row["id"]) for row in previous]
        if previous_ids:
            placeholders = ",".join("?" for _ in previous_ids)
            conn.execute(
                f"UPDATE driver_shift_distributions SET status='SUPERSEDED', updated_at=? WHERE organization_id=? AND id IN ({placeholders})",
                (now, organization_id, *previous_ids),
            )
            conn.execute(
                f"UPDATE driver_shift_distribution_recipients SET access_revoked_at=COALESCE(access_revoked_at, ?), updated_at=? WHERE organization_id=? AND distribution_id IN ({placeholders})",
                (now, now, organization_id, *previous_ids),
            )
            conn.execute(
                f"UPDATE driver_shift_distribution_portals SET status='REVOKED', revoked_at=COALESCE(revoked_at, ?), updated_at=? WHERE organization_id=? AND distribution_id IN ({placeholders})",
                (now, now, organization_id, *previous_ids),
            )
        cursor = conn.execute(
            """INSERT INTO driver_shift_distributions (
                   organization_id, driver_shift_planning_id, planning_version,
                   period_start, period_end, status, created_at, created_by, updated_at
               ) VALUES (?, ?, ?, ?, ?, 'READY', ?, ?, ?)""",
            (
                organization_id,
                planning["id"],
                planning["version"],
                period_start,
                period_end,
                now,
                actor,
                now,
            ),
        )
        distribution_id = int(cursor.lastrowid)
        conn.executemany(
            """INSERT INTO driver_shift_distribution_recipients (
                   public_id, organization_id, distribution_id, workforce_member_id,
                   delivery_status, access_status, access_token_hash,
                   access_generation, access_expires_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?, 'READY', 'NOT_OPENED', ?, ?, ?, ?, ?)""",
            [(item["public_id"], organization_id, distribution_id,
              item["workforce_member_id"], item["access_token_hash"],
              item["access_generation"], item["access_expires_at"], now, now)
             for item in recipients],
        )
        for previous_id in previous_ids:
            _audit(conn, organization_id, str(previous_id), actor,
                   "driver_shift_distribution_superseded", {"superseded_by": distribution_id})
        _audit(conn, organization_id, str(distribution_id), actor,
               "driver_shift_distribution_prepared", {
                   "planning_id": planning["id"], "planning_version": planning["version"],
                   "recipients": len(recipients), "period_start": period_start,
                   "period_end": period_end,
               })
        return _read_model_conn(conn, organization_id, distribution_id)


def distribution_for_planning(organization_id: str, planning_id: int) -> DriverShiftDistributionReadModel:
    with db_session() as conn:
        row = conn.execute(
            """SELECT id FROM driver_shift_distributions
               WHERE organization_id=? AND driver_shift_planning_id=?
               ORDER BY planning_version DESC, id DESC LIMIT 1""",
            (organization_id, planning_id),
        ).fetchone()
        if row is None:
            raise DriverShiftDistributionNotFoundError("Distribuzione turni non preparata.")
        return _read_model_conn(conn, organization_id, int(row["id"]))


def recipient_access(organization_id: str, distribution_id: int, recipient_id: int) -> dict:
    with db_session() as conn:
        row = conn.execute(
            """SELECT r.*, d.status distribution_status
               FROM driver_shift_distribution_recipients r
               JOIN driver_shift_distributions d
                 ON d.id=r.distribution_id AND d.organization_id=r.organization_id
               WHERE r.id=? AND r.distribution_id=? AND r.organization_id=?""",
            (recipient_id, distribution_id, organization_id),
        ).fetchone()
    if row is None:
        raise DriverShiftDistributionNotFoundError("Destinatario non trovato.")
    return {key: row[key] for key in row.keys()}


def batch_recipient_candidates(
    organization_id: str,
    distribution_id: int,
    recipient_ids: Sequence[int] | None = None,
) -> tuple[dict, list[dict]]:
    with db_session() as conn:
        distribution = conn.execute(
            "SELECT * FROM driver_shift_distributions WHERE id=? AND organization_id=?",
            (distribution_id, organization_id),
        ).fetchone()
        if distribution is None:
            raise DriverShiftDistributionNotFoundError("Distribuzione turni non trovata.")
        if distribution["status"] == "SUPERSEDED":
            raise DriverShiftDistributionError("Una distribuzione superata non può preparare batch.")
        parameters: list[object] = [organization_id, distribution_id]
        selected_clause = ""
        if recipient_ids is not None:
            if not recipient_ids:
                return ({key: distribution[key] for key in distribution.keys()}, [])
            placeholders = ",".join("?" for _ in recipient_ids)
            selected_clause = f" AND r.id IN ({placeholders})"
            parameters.extend(recipient_ids)
        rows = conn.execute(
            f"""SELECT r.*, m.display_name, m.first_name, m.phone, m.email,
                       d.status distribution_status
                FROM driver_shift_distribution_recipients r
                JOIN driver_shift_distributions d
                  ON d.id=r.distribution_id AND d.organization_id=r.organization_id
                JOIN workforce_members m
                  ON m.id=r.workforce_member_id AND m.organization_id=r.organization_id
                WHERE r.organization_id=? AND r.distribution_id=?{selected_clause}
                ORDER BY m.display_name, r.id""",
            tuple(parameters),
        ).fetchall()
    if recipient_ids is not None and len(rows) != len(set(recipient_ids)):
        raise DriverShiftDistributionNotFoundError(
            "Uno o più destinatari non appartengono alla distribuzione richiesta."
        )
    return (
        {key: distribution[key] for key in distribution.keys()},
        [{key: row[key] for key in row.keys()} for row in rows],
    )


def revoke_recipient(organization_id: str, distribution_id: int, recipient_id: int,
                     actor: str) -> DriverShiftDistributionReadModel:
    now = utc_now_iso()
    with db_session() as conn:
        changed = conn.execute(
            """UPDATE driver_shift_distribution_recipients
               SET access_revoked_at=COALESCE(access_revoked_at, ?), updated_at=?
               WHERE id=? AND distribution_id=? AND organization_id=?""",
            (now, now, recipient_id, distribution_id, organization_id),
        )
        if changed.rowcount == 0:
            raise DriverShiftDistributionNotFoundError("Destinatario non trovato.")
        _audit(conn, organization_id, str(recipient_id), actor,
               "driver_shift_recipient_access_revoked", {"distribution_id": distribution_id})
        return _read_model_conn(conn, organization_id, distribution_id)


def regenerate_recipient(organization_id: str, distribution_id: int, recipient_id: int,
                         generation: int, token_hash: str, expires_at: str,
                         actor: str) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        changed = conn.execute(
            """UPDATE driver_shift_distribution_recipients
               SET access_generation=?, access_token_hash=?, access_expires_at=?,
                   access_revoked_at=NULL, access_status='NOT_OPENED',
                   first_opened_at=NULL, last_opened_at=NULL, acknowledged_at=NULL,
                   delivery_status='READY', updated_at=?
               WHERE id=? AND distribution_id=? AND organization_id=?""",
            (generation, token_hash, expires_at, now, recipient_id,
             distribution_id, organization_id),
        )
        if changed.rowcount == 0:
            raise DriverShiftDistributionNotFoundError("Destinatario non trovato.")
        _audit(conn, organization_id, str(recipient_id), actor,
               "driver_shift_recipient_access_regenerated", {
                   "distribution_id": distribution_id, "generation": generation,
               })
        row = conn.execute(
            "SELECT * FROM driver_shift_distribution_recipients WHERE id=? AND organization_id=?",
            (recipient_id, organization_id),
        ).fetchone()
    assert row is not None
    return {key: row[key] for key in row.keys()}


def personal_view(token_hash: str, *, acknowledge: bool = False) -> PersonalDriverShiftView:
    now = utc_now_iso()
    with db_session() as conn:
        recipient = conn.execute(
            """SELECT r.*, d.driver_shift_planning_id, d.planning_version,
                      d.period_start, d.period_end, d.status distribution_status,
                      m.display_name
               FROM driver_shift_distribution_recipients r
               JOIN driver_shift_distributions d
                 ON d.id=r.distribution_id AND d.organization_id=r.organization_id
               JOIN workforce_members m
                 ON m.id=r.workforce_member_id AND m.organization_id=r.organization_id
               WHERE r.access_token_hash=? AND r.access_revoked_at IS NULL
                 AND r.access_expires_at >= ?
                 AND d.status IN ('READY', 'DISTRIBUTED')""",
            (token_hash, now),
        ).fetchone()
        if recipient is None:
            raise DriverShiftPersonalAccessNotFoundError("Accesso turni non disponibile.")
        if acknowledge:
            conn.execute(
                """UPDATE driver_shift_distribution_recipients
                   SET first_opened_at=COALESCE(first_opened_at, ?), last_opened_at=?,
                       acknowledged_at=COALESCE(acknowledged_at, ?),
                       access_status='ACKNOWLEDGED', updated_at=?
                   WHERE id=?""",
                (now, now, now, now, recipient["id"]),
            )
        else:
            conn.execute(
                """UPDATE driver_shift_distribution_recipients
                   SET first_opened_at=COALESCE(first_opened_at, ?), last_opened_at=?,
                       access_status=CASE WHEN acknowledged_at IS NULL THEN 'OPENED' ELSE 'ACKNOWLEDGED' END,
                       updated_at=? WHERE id=?""",
                (now, now, now, recipient["id"]),
            )
        refreshed = conn.execute(
            "SELECT * FROM driver_shift_distribution_recipients WHERE id=?",
            (recipient["id"],),
        ).fetchone()
        shifts = conn.execute(
            """SELECT operational_date, status_code, availability, shift_code,
                      start_time, end_time, station
               FROM driver_shift_planning_published_rows
               WHERE organization_id=? AND driver_shift_planning_id=?
                 AND planning_version=? AND workforce_member_id=?
                 AND operational_date BETWEEN ? AND ?
               ORDER BY operational_date, id""",
            (recipient["organization_id"], recipient["driver_shift_planning_id"],
             recipient["planning_version"], recipient["workforce_member_id"],
             recipient["period_start"], recipient["period_end"]),
        ).fetchall()
    assert refreshed is not None
    return PersonalDriverShiftView(
        driver_name=str(recipient["display_name"]),
        period_start=str(recipient["period_start"]), period_end=str(recipient["period_end"]),
        access_status=str(refreshed["access_status"]),
        first_opened_at=refreshed["first_opened_at"],
        acknowledged_at=refreshed["acknowledged_at"],
        shifts=[PersonalDriverShift(
            operational_date=row["operational_date"], status=row["status_code"],
            availability=bool(row["availability"]), shift=row["shift_code"],
            start_time=row["start_time"], end_time=row["end_time"],
            station=row["station"], notes=None,
        ) for row in shifts],
    )

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.plugins.dsp_workspace.domain.models import (
    DamageProjection,
    JournalProjection,
    OperationalRow,
    OperationalSignal,
)
from app.plugins.fleet.journal.control_room.completion_service import (
    _scheduled_at,
    _status,
)
from app.plugins.fleet.journal.domain.operational_day import (
    operational_bounds,
    organization_timezone,
)


BLOCKED_DAMAGE_STATES = {
    "indisponibile",
    "in_manutenzione",
    "in_officina",
    "fermo",
}
SEVERITY_RANK = {"bassa": 0, "media": 1, "alta": 2, "critica": 3}


@dataclass(frozen=True)
class OperationalProjectionResult:
    rows: list[OperationalRow]
    signals: list[OperationalSignal]
    journal_partial_rows: int = 0
    damage_partial_rows: int = 0


def _identity(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _journal_key(row: OperationalRow) -> tuple[int, str] | None:
    if row.vehicle.fleet_asset_id is None or row.driver.workforce_member_id is None:
        return None
    identifier = _identity(row.driver.planning_identifier)
    if not identifier:
        return None
    return row.vehicle.fleet_asset_id, identifier


def _procedure_state(
    records: list[dict],
    *,
    operation_type: str,
    row: OperationalRow,
    begins: datetime,
    ends: datetime,
    now: datetime,
) -> tuple[str, str | None]:
    relevant = [item for item in records if item["operation_type"] == operation_type]
    if any(item.get("movement_id") for item in relevant):
        return "completed", None
    scheduled = None
    scheduled_values = [item.get("scheduled_at") for item in relevant if item.get("scheduled_at")]
    if scheduled_values:
        scheduled = datetime.fromisoformat(str(max(scheduled_values)).replace("Z", "+00:00"))
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=begins.tzinfo)
    if scheduled is None:
        scheduled = _scheduled_at(
            {"cycle_or_wave": row.wave}, operation_type, begins, ends
        )
    critical = ends if operation_type == "check_in" else begins + timedelta(hours=8)
    temporal_state, _ = _status(now, scheduled, critical)
    if temporal_state == "atteso":
        return "pending", temporal_state
    return "missing", temporal_state


def _journal_projection(
    row: OperationalRow,
    records: list[dict],
    *,
    ambiguous: bool,
    source_available: bool,
    begins: datetime,
    ends: datetime,
    now: datetime,
) -> tuple[JournalProjection, list[OperationalSignal]]:
    if not source_available:
        return JournalProjection(available=False, partial=True), []
    key = _journal_key(row)
    if key is None or ambiguous:
        return JournalProjection(partial=True), []
    check_out, checkout_temporal = _procedure_state(
        records,
        operation_type="check_out",
        row=row,
        begins=begins,
        ends=ends,
        now=now,
    )
    check_in, _ = _procedure_state(
        records,
        operation_type="check_in",
        row=row,
        begins=begins,
        ends=ends,
        now=now,
    )
    in_progress = any(
        item.get("lifecycle_status") == "in_progress" and not item.get("movement_id")
        for item in records
    )
    anomaly = any(bool(item.get("anomaly_present")) for item in records)
    projection = JournalProjection(
        check_out_status=check_out,
        check_in_status=check_in,
        in_progress=in_progress,
        anomaly=anomaly,
    )
    values = {
        "assignment_id": row.assignment_id,
        "workforce_member_id": row.driver.workforce_member_id,
        "fleet_asset_id": row.vehicle.fleet_asset_id,
        "source": "journal",
    }
    signals: list[OperationalSignal] = []
    if check_out == "missing":
        signals.append(OperationalSignal(
            code="JOURNAL_CHECKOUT_MISSING",
            severity="critical" if checkout_temporal == "critico" else "warning",
            message="La presa in carico attesa non risulta completata.",
            **values,
        ))
    if check_in == "missing":
        signals.append(OperationalSignal(
            code="JOURNAL_CHECKIN_MISSING",
            severity="warning",
            message="Il rientro atteso non risulta completato.",
            **values,
        ))
    if anomaly:
        signals.append(OperationalSignal(
            code="JOURNAL_ANOMALY",
            severity="warning",
            message="Il Giornale di bordo segnala un'anomalia.",
            **values,
        ))
    if in_progress:
        signals.append(OperationalSignal(
            code="JOURNAL_IN_PROGRESS",
            severity="info",
            message="Una procedura del Giornale di bordo è in compilazione.",
            **values,
        ))
    return projection, signals


def _damage_projection(
    row: OperationalRow,
    cases: list[dict],
    *,
    source_available: bool,
) -> tuple[DamageProjection, list[OperationalSignal]]:
    if not source_available:
        return DamageProjection(available=False, partial=True), []
    if row.vehicle.fleet_asset_id is not None:
        relevant = [
            item for item in cases
            if int(item["vehicle_id"]) == row.vehicle.fleet_asset_id
        ]
        partial = False
    elif row.driver.workforce_member_id is not None:
        relevant = [
            item for item in cases
            if item.get("driver_workforce_member_id") is not None
            and int(item["driver_workforce_member_id"]) == row.driver.workforce_member_id
        ]
        partial = True
    else:
        relevant = []
        partial = True
    highest = max(
        (str(item.get("severity") or "") for item in relevant),
        key=lambda value: SEVERITY_RANK.get(value, -1),
        default=None,
    )
    blocked = any(
        str(item.get("vehicle_operational_status") or "") in BLOCKED_DAMAGE_STATES
        for item in relevant
    )
    projection = DamageProjection(
        open_cases_count=len(relevant),
        highest_severity=highest,
        vehicle_blocked=blocked,
        relevant_case_ids=[int(item["id"]) for item in relevant],
        partial=partial,
    )
    values = {
        "assignment_id": row.assignment_id,
        "workforce_member_id": row.driver.workforce_member_id,
        "fleet_asset_id": row.vehicle.fleet_asset_id,
        "source": "damage",
    }
    signals: list[OperationalSignal] = []
    if relevant:
        signals.append(OperationalSignal(
            code="OPEN_DAMAGE_CASE",
            severity="warning",
            message=(
                "1 pratica danno aperta."
                if len(relevant) == 1
                else f"{len(relevant)} pratiche danno aperte."
            ),
            **values,
        ))
    if blocked:
        signals.append(OperationalSignal(
            code="VEHICLE_BLOCKED_BY_DAMAGE",
            severity="critical",
            message="Il mezzo risulta fermo o non utilizzabile per danno.",
            **values,
        ))
    if highest in {"alta", "critica"}:
        signals.append(OperationalSignal(
            code="HIGH_SEVERITY_DAMAGE",
            severity="critical",
            message="È presente una pratica danno ad alta gravità.",
            **values,
        ))
    return projection, signals


def apply_operational_projections(
    *,
    rows: list[OperationalRow],
    journal_records: list[dict],
    damage_cases: list[dict],
    operation_date: str,
    timezone_name: str,
    operational_day_start_hour: int,
    journal_available: bool,
    damage_available: bool,
    now: datetime | None = None,
) -> OperationalProjectionResult:
    begins_utc, ends_utc = operational_bounds(
        date.fromisoformat(operation_date),
        timezone_name,
        operational_day_start_hour,
    )
    zone = organization_timezone(timezone_name)
    begins = begins_utc.astimezone(zone)
    ends = ends_utc.astimezone(zone)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(begins.tzinfo)

    records_by_key: dict[tuple[int, str], list[dict]] = defaultdict(list)
    records_by_asset: dict[int, list[dict]] = defaultdict(list)
    for record in journal_records:
        records_by_key[(int(record["asset_id"]), _identity(record["driver_identifier"]))].append(record)
        records_by_asset[int(record["asset_id"])].append(record)
    key_counts = Counter(key for row in rows if (key := _journal_key(row)) is not None)

    enriched: list[OperationalRow] = []
    signals: list[OperationalSignal] = []
    journal_partial_rows = 0
    damage_partial_rows = 0
    for row in rows:
        key = _journal_key(row)
        exact_records = records_by_key.get(key, []) if key else []
        unmatched_asset_identity = bool(
            key and not exact_records and records_by_asset.get(key[0])
        )
        journal, journal_signals = _journal_projection(
            row,
            exact_records,
            ambiguous=bool(
                (key and key_counts[key] > 1) or unmatched_asset_identity
            ),
            source_available=journal_available,
            begins=begins,
            ends=ends,
            now=current,
        )
        damage, damage_signals = _damage_projection(
            row,
            damage_cases,
            source_available=damage_available,
        )
        attention_codes = [
            *row.attention_codes,
            *(signal.code for signal in journal_signals),
            *(signal.code for signal in damage_signals),
        ]
        enriched.append(row.model_copy(update={
            "journal": journal,
            "damage": damage,
            "attention_codes": attention_codes,
        }))
        signals.extend(journal_signals)
        signals.extend(damage_signals)
        journal_partial_rows += int(journal.partial)
        damage_partial_rows += int(damage.partial)
    return OperationalProjectionResult(
        rows=enriched,
        signals=signals,
        journal_partial_rows=journal_partial_rows,
        damage_partial_rows=damage_partial_rows,
    )

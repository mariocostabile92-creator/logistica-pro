from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.auth import repository as auth_repository
from app.plugins.workforce.application import consecutivity_presenter
from app.plugins.workforce.domain.consecutivity import (
    ConsecutivityDay,
    ConsecutivitySnapshot,
)
from app.plugins.workforce.infrastructure import consecutivity_repository
from app.utils.date_utils import utc_now_iso


NON_WORKING = {"rest", "holiday", "sickness", "leave", "unavailable"}


def _organization_today(organization_id: str) -> date:
    row = auth_repository.organization_by_id(organization_id)
    timezone = row["timezone"] if row and row["timezone"] else "Europe/Rome"
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        return datetime.now(ZoneInfo("Europe/Rome")).date()


def _is_partial_leave(row: dict) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("notes", "shift_code")).casefold()
    return row.get("status_code") == "leave" and (
        bool(row.get("start_time") or row.get("end_time")) or "parzial" in text
    )


def _put(facts, driver: str, day: str, *, state: str, source: str, priority: int, reason: str):
    current = facts[driver].get(day)
    if current is None or priority > current["priority"]:
        facts[driver][day] = {
            "state": state, "source": source, "priority": priority, "reason": reason,
        }


def _facts(rows: dict[str, list[dict]], members, today: date):
    facts = defaultdict(dict)
    sources = defaultdict(set)
    member_ids = {member.external_identifier: member for member in members}
    finalized: dict[str, str] = {}
    for item in rows["finalized_days"]:
        current = finalized.get(item["operation_date"])
        if current != "published":
            finalized[item["operation_date"]] = item["status"]
    planned_by_day = defaultdict(set)
    for item in rows["plannings"]:
        driver = item["driver_id"]
        if driver not in member_ids:
            continue
        day = item["operation_date"]
        planned_by_day[day].add(driver)
        source = f"planning_{item['status']}"
        if date.fromisoformat(day) < today:
            _put(facts, driver, day, state="worked", source=source, priority=300 if item["status"] == "published" else 250, reason="Assegnazione Planning finalizzata trascorsa.")
        else:
            _put(facts, driver, day, state="planned", source=source, priority=200 if item["status"] == "published" else 150, reason="Assegnazione Planning finalizzata.")
        sources[driver].add(source)
    for day, planning_status in finalized.items():
        for driver in member_ids:
            if driver not in planned_by_day[day]:
                _put(facts, driver, day, state="not_assigned", source=f"planning_{planning_status}", priority=40, reason="Nessuna assegnazione nel Planning finalizzato.")
    for item in rows["statuses"]:
        driver = item["external_identifier"]
        day = item["date"]
        code = item["status_code"]
        if code == "scheduled" and date.fromisoformat(day) < today:
            _put(facts, driver, day, state="worked", source="workforce_history", priority=100, reason="Turno storico Workforce confermato o importato.")
            sources[driver].add("workforce_history")
        elif code in NON_WORKING and not _is_partial_leave(item):
            _put(facts, driver, day, state=code, source="workforce_status", priority=350, reason=f"Stato Workforce: {code}.")
            sources[driver].add("workforce_status")
        elif _is_partial_leave(item):
            sources[driver].add("workforce_partial_leave")
    for item in rows["journal"]:
        driver = item["declared_driver_identifier"]
        if driver not in member_ids:
            continue
        _put(facts, driver, item["operation_date"], state="worked", source="journal_completed", priority=500, reason="Movimentazione Driver Journal completata.")
        sources[driver].add("journal_completed")
    return facts, sources


def _has_complete_break(
    facts: dict[str, dict],
    break_end: date,
    allowed: set[str],
    rest_break_days: int,
) -> bool:
    for offset in range(max(rest_break_days, 1)):
        fact = facts.get((break_end - timedelta(days=offset)).isoformat())
        if not fact or fact["state"] in allowed:
            return False
    return True


def _trailing(
    facts: dict[str, dict],
    anchor: date,
    allowed: set[str],
    window_start: date,
    rest_break_days: int,
) -> tuple[int | None, bool]:
    candidates = sorted(
        (date.fromisoformat(day) for day, fact in facts.items() if date.fromisoformat(day) <= anchor and fact["state"] in allowed),
        reverse=True,
    )
    if not candidates:
        immediate = facts.get(anchor.isoformat())
        if immediate and immediate["state"] not in allowed and _has_complete_break(
            facts, anchor, allowed, rest_break_days
        ):
            return 0, True
        return None, False
    cursor = candidates[0]
    count = 0
    while cursor >= window_start:
        fact = facts.get(cursor.isoformat())
        if fact and fact["state"] in allowed:
            count += 1
            cursor -= timedelta(days=1)
            continue
        if fact and fact["state"] not in allowed:
            return count, _has_complete_break(
                facts, cursor, allowed, rest_break_days
            )
        return count, False
    return count, False


def snapshots(
    organization_id: str,
    operation_date: str,
    members,
    *,
    today: date | None = None,
) -> dict[int, ConsecutivitySnapshot]:
    target = date.fromisoformat(operation_date)
    current_day = today or _organization_today(organization_id)
    date_from, date_to = consecutivity_repository.analysis_window(operation_date)
    rows = consecutivity_repository.source_rows(organization_id, date_from, date_to)
    policy = consecutivity_repository.get_policy(organization_id)
    overrides = consecutivity_repository.active_overrides(organization_id, operation_date)
    expired_overrides = consecutivity_repository.expired_overrides(
        organization_id, operation_date
    )
    facts, source_names = _facts(rows, members, current_day)
    result = {}
    effective_anchor = min(target - timedelta(days=1), current_day - timedelta(days=1))
    for member in members:
        driver_facts = facts[member.external_identifier]
        effective, effective_ok = _trailing(
            driver_facts,
            effective_anchor,
            {"worked"},
            date.fromisoformat(date_from),
            policy.rest_break_days,
        )
        planned, planned_ok = _trailing(
            driver_facts,
            target,
            {"worked", "planned"},
            date.fromisoformat(date_from),
            policy.rest_break_days,
        )
        if not any(fact["state"] == "planned" for fact in driver_facts.values()):
            planned, planned_ok = effective, effective_ok
        evaluated_count = planned if planned is not None else effective
        calculated_status, reason = consecutivity_presenter.evaluation(
            evaluated_count, effective_ok and planned_ok, policy
        )
        override = overrides.get(member.workforce_member_id)
        status = "override_manual" if override else calculated_status
        if override:
            reason = f"Override manuale: {override.reason}"
        last_worked = max(
            (day for day, fact in driver_facts.items() if fact["state"] == "worked"),
            default=None,
        )
        last_rest = max(
            (day for day, fact in driver_facts.items() if fact["state"] == "rest" and day < operation_date),
            default=None,
        )
        next_planned = min(
            (day for day, fact in driver_facts.items() if fact["state"] == "planned" and day >= current_day.isoformat()),
            default=None,
        )
        sequence_from = target - timedelta(days=7)
        sequence_to = target + timedelta(days=6)
        sequence = []
        cursor = sequence_from
        while cursor <= sequence_to:
            day = cursor.isoformat()
            fact = driver_facts.get(day)
            if fact:
                sequence.append(ConsecutivityDay(
                    date=day, state=fact["state"], source=fact["source"],
                    worked=fact["state"] == "worked", planned=fact["state"] == "planned",
                    reason=fact["reason"],
                ))
            else:
                sequence.append(ConsecutivityDay(
                    date=day, state="missing", source="none", reason="Dato non disponibile."
                ))
            cursor += timedelta(days=1)
        result[member.workforce_member_id] = ConsecutivitySnapshot(
            driver_id=member.workforce_member_id,
            operation_date=operation_date,
            organization_id=organization_id,
            effective_consecutive_days=effective if effective_ok else None,
            planned_consecutive_days=planned if planned_ok else None,
            last_worked_date=last_worked,
            last_rest_date=last_rest,
            next_planned_work_date=next_planned,
            threshold_warning=policy.warning_threshold,
            threshold_rest_required=policy.rest_required_threshold,
            status=status,
            calculated_status=calculated_status,
            reason=reason,
            source_summary=sorted(source_names[member.external_identifier]),
            calculated_at=utc_now_iso(),
            analyzed_from=date_from,
            analyzed_to=effective_anchor.isoformat(),
            sequence=sequence,
            override=override,
            expired_override=(
                expired_overrides.get(member.workforce_member_id)
                if not override else None
            ),
        )
    return result

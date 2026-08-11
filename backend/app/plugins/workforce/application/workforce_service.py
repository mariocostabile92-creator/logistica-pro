import csv
import io
from datetime import date, timedelta
from hashlib import sha256
import logging
from time import perf_counter

from app.domain.core_language.models import (
    HumanResource,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.plugins.workforce.application.configuration import (
    workforce_status_configuration,
)
from app.plugins.workforce.domain.errors import WorkforceValidationError
from app.plugins.workforce.domain.models import (
    WorkforceBriefingSnapshot,
    WorkforceCoverage,
)
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import (
    import_repository,
    read_repository,
    write_repository,
)
from app.plugins.workforce.application.preview_cache import WorkforcePreviewCache


logger = logging.getLogger(__name__)
preview_cache = WorkforcePreviewCache()


def preview_import(content: bytes, filename: str):
    parsed = interpret_workforce_workbook(content, filename)
    preview_cache.store(parsed)
    logger.info(
        "Workforce preview completed stages=%s members=%s statuses=%s",
        {key: round(value, 4) for key, value in parsed.metrics.items()},
        len(parsed.members),
        len(parsed.statuses),
    )
    return parsed.preview


def apply_import(
    content: bytes,
    filename: str,
    confirmed_fingerprint: str,
    actor: str = "local_operator",
):
    fingerprint_started = perf_counter()
    actual_fingerprint = sha256(content).hexdigest()
    fingerprint_seconds = perf_counter() - fingerprint_started
    if actual_fingerprint != confirmed_fingerprint:
        from app.plugins.workforce.domain.errors import WorkforceImportConfirmationError
        raise WorkforceImportConfirmationError(
            "Il file e cambiato dopo la preview. Analizzalo nuovamente."
        )
    prior = read_repository.imported_result(actual_fingerprint)
    if prior:
        preview_cache.discard(actual_fingerprint)
        return prior
    parsed = preview_cache.get(actual_fingerprint)
    cache_hit = parsed is not None
    if parsed is None:
        parsed = interpret_workforce_workbook(content, filename)
    if not parsed.members:
        raise WorkforceValidationError(
            "Nessuna risorsa Workforce importabile e stata rilevata."
        )
    metrics = dict(parsed.metrics)
    metrics["fingerprint"] = fingerprint_seconds
    metrics["preview_cache_hit"] = float(cache_hit)
    result = import_repository.apply_import(
        parsed,
        original_filename=filename,
        actor=actor,
        metrics=metrics,
    )
    preview_cache.discard(actual_fingerprint)
    logger.info(
        "Workforce import completed stages=%s members=%s statuses=%s",
        {key: round(value, 4) for key, value in metrics.items()},
        len(parsed.members),
        len(parsed.statuses),
    )
    return result


def list_members(organization_id: str | None = None):
    return read_repository.list_members(organization_id)


def list_calendar(date_from: str | None = None, date_to: str | None = None, member_id: int | None = None, organization_id: str | None = None):
    return read_repository.list_statuses(date_from, date_to, member_id, organization_id)


def _allowed_statuses() -> set[str]:
    values = workforce_status_configuration().get("allowed", [])
    configured = {str(item) for item in values} if isinstance(values, list) else set()
    return configured | {"available_limited"}


def _normalized_day_status(values: dict[str, object]) -> dict[str, object]:
    normalized = dict(values)
    status_code = str(normalized["status_code"])
    if status_code not in _allowed_statuses():
        raise WorkforceValidationError(
            "Lo stato Workforce non e previsto dalla configurazione corrente."
        )
    if status_code == "available_limited" and not str(normalized.get("notes") or "").strip():
        raise WorkforceValidationError(
            "La disponibilita con limitazioni richiede una motivazione."
        )
    if normalized.get("availability") is None:
        configured = workforce_status_configuration().get(
            "available_statuses", ["available", "available_limited", "scheduled"]
        )
        available_statuses = {
            str(item) for item in configured
        } if isinstance(configured, list) else {"available", "scheduled"}
        available_statuses.add("available_limited")
        normalized["availability"] = status_code in available_statuses
    return normalized


def save_day_status(values: dict[str, object], actor: str, status_id: int | None = None, organization_id: str = "default"):
    normalized = _normalized_day_status(values)
    return write_repository.save_manual_status(normalized, actor, status_id, organization_id)


def save_day_statuses_batch(
    values: dict[str, object],
    actor: str,
    organization_id: str = "default",
):
    normalized = _normalized_day_status(values)
    dates = [str(item) for item in normalized.pop("dates", [])]
    if not dates or len(set(dates)) != len(dates):
        raise WorkforceValidationError("Le date selezionate non sono valide.")
    return write_repository.save_manual_statuses_batch(
        normalized,
        dates,
        actor,
        organization_id,
    )


def update_member(member_id: int, changes: dict[str, object], actor: str, organization_id: str = "default"):
    if not changes:
        raise WorkforceValidationError("Nessuna modifica specificata.")
    return write_repository.update_member(member_id, changes, actor, organization_id)


def coverage(date_from: str | None = None, date_to: str | None = None):
    statuses = read_repository.list_statuses(date_from, date_to)
    requirements = read_repository.list_requirements(date_from, date_to)
    days = sorted({item.date for item in statuses} | {item.date for item in requirements})
    requirement_by_day: dict[str, int] = {}
    for item in requirements:
        requirement_by_day[item.date] = requirement_by_day.get(item.date, 0) + item.required_resources
    result = []
    for day in days:
        daily = [item for item in statuses if item.date == day]
        available = sum(item.availability for item in daily)
        scheduled = sum(item.status_code == "scheduled" for item in daily)
        unavailable = len(daily) - available
        required = requirement_by_day.get(day)
        if required is None:
            status = "requirement_unavailable"
            margin = None
            limitations = ["Fabbisogno non disponibile."]
        else:
            margin = available - required
            status = "covered" if margin >= 0 else "deficit"
            limitations = []
        result.append(
            WorkforceCoverage(
                date=day,
                required=required,
                available=available,
                scheduled=scheduled,
                unavailable=unavailable,
                margin=margin,
                status=status,
                limitations=limitations,
            )
        )
    return result


def list_changes(limit: int = 100):
    return read_repository.list_changes(limit)


def core_contracts(date_from: str | None = None, date_to: str | None = None):
    members = {item.workforce_member_id: item for item in list_members()}
    human_resources = [
        HumanResource(
            external_identifier=item.external_identifier,
            display_name=item.display_name,
            capabilities=tuple(item.capabilities),
        )
        for item in members.values()
    ]
    availability = []
    for item in list_calendar(date_from, date_to):
        member = members.get(item.workforce_member_id)
        if not member:
            continue
        availability.append({
            "resource": ResourceAvailability(
                resource_identifier=member.external_identifier,
                resource_kind=ResourceKind.HUMAN_RESOURCE,
                available=item.availability,
                observed_state=item.status_code,
            ),
            "time_window": TimeWindow(
                external_identifier=item.date,
                starts_at=item.start_time,
                ends_at=item.end_time,
            ),
        })
    return {"human_resources": human_resources, "availability": availability}


def briefing_snapshot(operation_date: str) -> WorkforceBriefingSnapshot | None:
    items = coverage(operation_date, operation_date)
    if not items:
        return None
    members = list_members()
    daily = list_calendar(operation_date, operation_date)
    requirements = read_repository.list_requirements(operation_date, operation_date)
    available_member_ids = {item.workforce_member_id for item in daily if item.availability}
    available_capabilities = {
        capability
        for member in members
        if member.workforce_member_id in available_member_ids
        for capability in member.capabilities
    }
    required_capabilities = {
        capability for item in requirements for capability in item.required_capabilities
    }
    limit = date.fromisoformat(operation_date) + timedelta(days=30)
    return WorkforceBriefingSnapshot(
        date=operation_date,
        coverage=items[0],
        absences=sum(not item.availability for item in daily),
        contracts_expiring=sum(
            bool(member.contract_end)
            and date.fromisoformat(member.contract_end) <= limit
            and date.fromisoformat(member.contract_end) >= date.fromisoformat(operation_date)
            for member in members
        ),
        missing_capabilities=sorted(required_capabilities - available_capabilities),
    )


def export_csv(section: str = "calendar") -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if section == "coverage":
        writer.writerow(["date", "required", "available", "scheduled", "unavailable", "margin", "status"])
        for item in coverage():
            writer.writerow([item.date, item.required, item.available, item.scheduled, item.unavailable, item.margin, item.status])
    elif section == "changes":
        writer.writerow(["timestamp", "entity_type", "entity_id", "reason", "source"])
        for item in list_changes(1000):
            writer.writerow([item.timestamp, item.entity_type, item.entity_id, item.reason, item.source])
    else:
        members = {item.workforce_member_id: item for item in list_members()}
        writer.writerow(["resource_identifier", "display_name", "date", "status", "available", "shift", "notes", "origin"])
        for item in list_calendar():
            member = members.get(item.workforce_member_id)
            writer.writerow([
                member.external_identifier if member else item.workforce_member_id,
                member.display_name if member else "",
                item.date, item.status_code, item.availability,
                item.shift_code, item.notes, item.observed_or_confirmed.value,
            ])
    return output.getvalue()

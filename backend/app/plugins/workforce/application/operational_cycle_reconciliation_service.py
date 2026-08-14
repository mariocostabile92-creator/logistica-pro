from collections import Counter, defaultdict
from hashlib import sha256
import json
import sqlite3

from app.importers.workbook_profiler.workbook_scanner import scan_workbook
from app.plugins.workforce.domain.operational_cycle_reconciliation import (
    OperationalCycleCoverageImpact,
    OperationalCycleReconciliationDetail,
    OperationalCycleReconciliationPreview,
    OperationalCycleReconciliationResult,
    OperationalCycleReconciliationSummary,
    OperationalCycleResolutionStatus,
)
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import (
    legacy_coverage_backfill_repository,
    operational_cycle_reconciliation_repository as repository,
)


COVERAGE_FROM = "2026-08-10"
COVERAGE_TO = "2026-08-16"
_CODES = {
    ("NEXT_DAY", None): frozenset({"C1", "L1", "L2", "L3", "VMC1"}),
    ("SAME_DAY", "A"): frozenset({"SA"}),
    ("SAME_DAY", "B_C"): frozenset({"SB"}),
}


class OperationalCycleReconciliationError(ValueError):
    pass


class OperationalCycleReconciliationConflictError(
    OperationalCycleReconciliationError
):
    pass


def _key(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _cycle(value: object) -> str | None:
    normalized = _key(value).replace("-", " ").replace("_", " ")
    compact = normalized.replace(" ", "")
    if compact in {"next", "nextday", "nd"}:
        return "NEXT_DAY"
    if compact in {
        "sameday", "sd", "mattino", "pomeriggio", "samedaya",
        "samedayb", "samedaybc",
    }:
        return "SAME_DAY"
    return None


def _explicit_rows(content: bytes, filename: str, parsed) -> list[dict[str, object]]:
    workbook = scan_workbook(content, filename)
    planning = next(
        (sheet for sheet in workbook.sheets if _key(sheet.name) == "planning"),
        None,
    )
    if planning is None:
        raise OperationalCycleReconciliationError(
            "Il workbook non contiene il foglio Planning autorevole."
        )
    source_rows = {
        row.source_row_number: row
        for row in parsed.source_rows
        if row.source_sheet == planning.name and row.row_kind == "identity"
    }
    if not source_rows:
        raise OperationalCycleReconciliationError(
            "Il foglio Planning non contiene identita driver utilizzabili."
        )
    header_number = min(source_rows) - 1
    header = planning.rows[header_number - 1]
    turn_index = next(
        (index for index, value in enumerate(header) if _key(value) == "turno"),
        None,
    )
    if turn_index is None:
        raise OperationalCycleReconciliationError(
            "La colonna Planning.Turno non e disponibile."
        )
    result = []
    for number, source in sorted(source_rows.items()):
        values = planning.rows[number - 1]
        evidence = str(values[turn_index] or "").strip()
        result.append({
            "source": source,
            "evidence_value": evidence or None,
            "proposed_cycle": _cycle(evidence),
        })
    return result


def _resolve(
    source_rows: list[dict[str, object]],
    member_rows: list[dict[str, object]],
    transporter: dict[str, list[int]],
    imported_transporter: dict[str, list[int]],
    workbook_name: str,
) -> list[OperationalCycleReconciliationDetail]:
    by_id = {int(row["id"]): row for row in member_rows}
    by_external: dict[str, list[int]] = defaultdict(list)
    by_name: dict[str, list[int]] = defaultdict(list)
    for row in member_rows:
        by_external[_key(row["external_identifier"])].append(int(row["id"]))
        by_name[_key(row["display_name"])].append(int(row["id"]))
    provisional: list[tuple[dict[str, object], set[int], str | None]] = []
    referenced_member_ids: set[int] = set()
    for item in source_rows:
        source = item["source"]
        candidates: set[int] = set()
        sources: list[str] = []
        external = _key(source.resolution_identifier)
        if external and by_external.get(external):
            candidates.update(by_external[external])
            sources.append("workforce_external_identifier")
        tid = _key(source.transporter_id)
        if tid and transporter.get(tid):
            candidates.update(transporter[tid])
            sources.append("amazon_transporter")
        if tid and imported_transporter.get(tid):
            candidates.update(imported_transporter[tid])
            sources.append("workforce_import_row")
        name = _key(source.driver_display_name)
        if not candidates and name and by_name.get(name):
            candidates.update(by_name[name])
            sources.append("exact_normalized_identity")
        referenced_member_ids.update(candidates)
        provisional.append((item, candidates, "+".join(sources) or None))

    member_cycles: dict[int, set[str]] = defaultdict(set)
    for item, candidates, _ in provisional:
        cycle = item["proposed_cycle"]
        if len(candidates) == 1 and cycle:
            member_cycles[next(iter(candidates))].add(str(cycle))

    details = []
    for item, candidates, resolution_source in provisional:
        source = item["source"]
        proposed = item["proposed_cycle"]
        member = by_id[next(iter(candidates))] if len(candidates) == 1 else None
        if not proposed:
            status = OperationalCycleResolutionStatus.NO_CYCLE_EVIDENCE
            explanation = "Planning.Turno non contiene un ciclo esplicito supportato."
        elif not candidates:
            status = OperationalCycleResolutionStatus.NOT_FOUND
            explanation = "Nessun membro Workforce organization-scoped corrisponde."
        elif len(candidates) > 1:
            status = OperationalCycleResolutionStatus.AMBIGUOUS
            explanation = "Le fonti identita conducono a piu membri Workforce."
        elif len(member_cycles[int(member["id"])]) > 1:
            status = OperationalCycleResolutionStatus.CONFLICT
            explanation = "La sorgente propone cicli discordanti per lo stesso membro."
        elif member["operational_cycle"] not in {"NOT_SET", proposed}:
            status = OperationalCycleResolutionStatus.CONFLICT
            explanation = "Il ciclo esistente e diverso dall'evidenza del workbook."
        else:
            status = OperationalCycleResolutionStatus.RESOLVED
            explanation = "Identita unica e ciclo esplicito Planning.Turno."
        eligible = bool(
            status == OperationalCycleResolutionStatus.RESOLVED
            and member is not None
            and member["operational_cycle"] == "NOT_SET"
        )
        details.append(OperationalCycleReconciliationDetail(
            workbook_name=workbook_name,
            workbook_driver_name=source.driver_display_name,
            transporter_id=source.transporter_id,
            source_reference=source.source_reference,
            evidence_value=item["evidence_value"],
            proposed_cycle=proposed,
            workforce_member_id=(int(member["id"]) if member else None),
            workforce_external_identifier=(
                str(member["external_identifier"]) if member else None
            ),
            workforce_display_name=(str(member["display_name"]) if member else None),
            current_cycle=(str(member["operational_cycle"]) if member else None),
            status=status,
            resolution_source=resolution_source,
            apply_eligible=eligible,
            explanation=explanation,
        ))
    for member_id, member in sorted(by_id.items()):
        if member_id in referenced_member_ids:
            continue
        details.append(OperationalCycleReconciliationDetail(
            workbook_name=workbook_name,
            workforce_member_id=member_id,
            workforce_external_identifier=str(member["external_identifier"]),
            workforce_display_name=str(member["display_name"]),
            current_cycle=str(member["operational_cycle"]),
            status=OperationalCycleResolutionStatus.NO_CYCLE_EVIDENCE,
            apply_eligible=False,
            explanation=(
                "Nessuna riga driver nel foglio Planning autorevole "
                "corrisponde al membro Workforce."
            ),
        ))
    return details


def _coverage_impact(
    organization_id: str,
    details: list[OperationalCycleReconciliationDetail],
) -> list[OperationalCycleCoverageImpact]:
    statuses, requirements = repository.coverage_inputs(
        organization_id, COVERAGE_FROM, COVERAGE_TO
    )
    overrides = {
        item.workforce_member_id: item.proposed_cycle
        for item in details if item.apply_eligible
    }
    result = []
    for requirement in requirements:
        cycle = str(requirement["operational_cycle"])
        segment = requirement["coverage_segment"]
        codes = _CODES.get((cycle, segment), frozenset())
        station_key = _key(requirement["station"])

        def count(after: bool) -> int:
            total = 0
            for status in statuses:
                effective = (
                    overrides.get(int(status["workforce_member_id"]))
                    if after else None
                ) or status["operational_cycle"]
                if (
                    status["date"] == requirement["operational_date"]
                    and bool(status["availability"])
                    and status["shift_code"] in codes
                    and effective == cycle
                    and (not station_key or _key(status["station"]) == station_key)
                ):
                    total += 1
            return total

        result.append(OperationalCycleCoverageImpact(
            operational_date=str(requirement["operational_date"]),
            cycle=cycle,
            segment=(str(segment) if segment else None),
            station=(str(requirement["station"]) if requirement["station"] else None),
            forecast_routes=int(requirement["forecast_routes"]),
            required_capacity=int(requirement["required_capacity"]),
            assigned_before=count(False),
            assigned_after=count(True),
        ))
    return result


def _summary(
    members: list[dict[str, object]],
    details: list[OperationalCycleReconciliationDetail],
) -> OperationalCycleReconciliationSummary:
    statuses = Counter(item.status for item in details)
    return OperationalCycleReconciliationSummary(
        workforce_total=len(members),
        currently_not_set=sum(row["operational_cycle"] == "NOT_SET" for row in members),
        resolved_next_day=sum(
            item.status == OperationalCycleResolutionStatus.RESOLVED
            and item.proposed_cycle == "NEXT_DAY" for item in details
        ),
        resolved_same_day=sum(
            item.status == OperationalCycleResolutionStatus.RESOLVED
            and item.proposed_cycle == "SAME_DAY" for item in details
        ),
        ambiguous=statuses[OperationalCycleResolutionStatus.AMBIGUOUS],
        not_found=statuses[OperationalCycleResolutionStatus.NOT_FOUND],
        conflicts=statuses[OperationalCycleResolutionStatus.CONFLICT],
        no_cycle_evidence=statuses[
            OperationalCycleResolutionStatus.NO_CYCLE_EVIDENCE
        ],
        unchanged_existing_cycles=sum(
            item.status == OperationalCycleResolutionStatus.RESOLVED
            and item.current_cycle == item.proposed_cycle
            and not item.apply_eligible for item in details
        ),
        apply_eligible=sum(item.apply_eligible for item in details),
    )


def _fingerprint(preview: OperationalCycleReconciliationPreview) -> str:
    payload = preview.model_dump(mode="json", exclude={"preview_fingerprint"})
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def preview(
    organization_id: str,
    *,
    content: bytes,
    filename: str,
    workforce_import_id: int,
) -> OperationalCycleReconciliationPreview:
    import_record = legacy_coverage_backfill_repository.find_import(
        organization_id, workforce_import_id=workforce_import_id
    )
    if import_record is None:
        raise OperationalCycleReconciliationError(
            "Import Workforce non trovato nell'organizzazione corrente."
        )
    actual = sha256(content).hexdigest()
    if actual != import_record["fingerprint"]:
        raise OperationalCycleReconciliationError(
            "Il workbook non corrisponde al fingerprint dell'import selezionato."
        )
    parsed = interpret_workforce_workbook(content, filename)
    source_rows = _explicit_rows(content, filename, parsed)
    member_rows = repository.members(organization_id)
    details = _resolve(
        source_rows,
        member_rows,
        repository.transporter_identities(organization_id),
        repository.imported_transporter_identities(
            organization_id, workforce_import_id
        ),
        str(import_record["original_filename"]),
    )
    summary = _summary(member_rows, details)
    result = OperationalCycleReconciliationPreview(
        status="READY" if summary.apply_eligible else "ALREADY_COMPLETE",
        workforce_import_id=workforce_import_id,
        original_filename=str(import_record["original_filename"]),
        source_filename=filename,
        import_fingerprint=actual,
        summary=summary,
        details=details,
        coverage_impact=_coverage_impact(organization_id, details),
        action_required=(
            "Confermare esclusivamente i membri RESOLVED ancora NOT_SET."
            if summary.apply_eligible else "Nessuna scrittura necessaria."
        ),
    )
    return result.model_copy(update={"preview_fingerprint": _fingerprint(result)})


def apply(
    organization_id: str,
    *,
    content: bytes,
    filename: str,
    workforce_import_id: int,
    expected_preview_fingerprint: str,
    actor: str,
) -> OperationalCycleReconciliationResult:
    inspection = preview(
        organization_id,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
    )
    if inspection.preview_fingerprint != expected_preview_fingerprint:
        raise OperationalCycleReconciliationConflictError(
            "La preview e obsoleta: sorgente o stato Workforce sono cambiati."
        )
    changes = [item.model_dump() for item in inspection.details if item.apply_eligible]
    try:
        updated, audits = repository.apply_cycles(
            organization_id,
            changes,
            actor=actor,
            workforce_import_id=workforce_import_id,
            source_filename=inspection.original_filename or filename,
        )
    except sqlite3.IntegrityError as exc:
        raise OperationalCycleReconciliationConflictError(str(exc)) from exc
    final = preview(
        organization_id,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
    )
    return OperationalCycleReconciliationResult(
        **final.model_dump(),
        members_updated=updated,
        audit_events_created=audits,
        idempotent=updated == 0,
    )

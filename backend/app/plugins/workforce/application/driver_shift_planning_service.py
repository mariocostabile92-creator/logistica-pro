from collections import defaultdict
from datetime import date

from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningError,
    DriverShiftPlanningMergePreview,
    DriverShiftPlanningMergeRow,
    DriverShiftPlanningMergeSummary,
    DriverShiftPlanningSource,
    DriverShiftPlanningSourceNotFoundError,
    DriverShiftPlanningSourceStatus,
    MergeAlternative,
    MergeClassification,
    MergeSourceReference,
)
from app.plugins.workforce.infrastructure import driver_shift_planning_repository as repository


def _iso_date(value: str, field: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise DriverShiftPlanningError(f"{field} non valida.") from exc


def create_driver_shift_planning(
    organization_id: str,
    period_start: str,
    period_end: str,
    label: str | None = None,
    actor: str = "local_operator",
) -> DriverShiftPlanning:
    start = _iso_date(period_start, "period_start")
    end = _iso_date(period_end, "period_end")
    if start > end:
        raise DriverShiftPlanningError("period_start deve precedere period_end.")
    normalized_label = label.strip() if label and label.strip() else None
    if normalized_label and len(normalized_label) > 160:
        raise DriverShiftPlanningError("Label troppo lunga.")
    if not actor.strip():
        raise DriverShiftPlanningError("Actor obbligatorio.")
    return repository.create_planning(
        organization_id, start, end, normalized_label, actor.strip()
    )


def _source_spec(
    planning: DriverShiftPlanning,
    workforce_import_id: int,
) -> tuple[dict[str, object], str]:
    facts = repository.source_facts(
        planning.organization_id, workforce_import_id
    )
    if facts is None:
        raise DriverShiftPlanningSourceNotFoundError(
            "Workforce import non trovato nella stessa organizzazione."
        )
    if int(facts["source_row_count"] or 0) == 0:
        return facts, DriverShiftPlanningSourceStatus.UNAVAILABLE_FOR_MERGE.value
    date_from = str(facts["date_from"])
    date_to = str(facts["date_to"])
    if date_to < planning.period_start or date_from > planning.period_end:
        raise DriverShiftPlanningError(
            "La source non ha sovrapposizione con il periodo del planning."
        )
    return facts, DriverShiftPlanningSourceStatus.AVAILABLE.value


def add_source(
    organization_id: str,
    logical_planning_id: int,
    workforce_import_id: int,
    *,
    actor: str = "local_operator",
    source_order: int | None = None,
) -> DriverShiftPlanningSource:
    planning = repository.get_planning(organization_id, logical_planning_id)
    _, status = _source_spec(planning, workforce_import_id)
    sources = repository.list_sources(organization_id, logical_planning_id)
    if source_order is None:
        source_order = max((item.source_order for item in sources), default=-1) + 1
    if source_order < 0:
        raise DriverShiftPlanningError("source_order non può essere negativo.")
    relation_id = repository.add_source_record(
        organization_id,
        logical_planning_id,
        workforce_import_id,
        source_order,
        status,
        actor,
    )
    return next(
        item
        for item in repository.list_sources(organization_id, logical_planning_id)
        if item.id == relation_id
    )


def remove_source(
    organization_id: str,
    logical_planning_id: int,
    source_id: int,
) -> None:
    repository.remove_source_record(
        organization_id, logical_planning_id, source_id
    )


def replace_sources(
    organization_id: str,
    logical_planning_id: int,
    workforce_import_ids: list[int],
    *,
    actor: str = "local_operator",
) -> list[DriverShiftPlanningSource]:
    if len(set(workforce_import_ids)) != len(workforce_import_ids):
        raise DriverShiftPlanningError("Una source non può essere ripetuta.")
    planning = repository.get_planning(organization_id, logical_planning_id)
    specs = []
    for order, import_id in enumerate(workforce_import_ids):
        _, status = _source_spec(planning, import_id)
        specs.append((import_id, order, status))
    repository.replace_source_records(
        organization_id, logical_planning_id, specs, actor
    )
    return repository.list_sources(organization_id, logical_planning_id)


def _normalized(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, int):
        return bool(value)
    return value


def _identity_key(row: dict[str, object]) -> str | None:
    if row["resolved_workforce_member_id"] is not None:
        return f"member:{int(row['resolved_workforce_member_id'])}"
    external = str(row["source_external_identifier"] or "").strip()
    return f"external:{external.casefold()}" if external else None


def _operational_values(row: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        _normalized(row[field])
        for field in (
            "status_code", "availability", "shift_code", "start_time",
            "end_time", "station", "notes",
        )
    )


def _reference(row: dict[str, object]) -> MergeSourceReference:
    return MergeSourceReference(
        workforce_import_id=int(row["workforce_import_id"]),
        filename=str(row["source_filename"]),
        sheet=str(row["source_sheet"]),
        row_number=int(row["source_row_number"]),
        source_record_key=str(row["source_record_key"]),
        source_order=int(row["source_order"]),
    )


def _alternative(
    rows: list[dict[str, object]],
) -> MergeAlternative:
    candidate = rows[0]
    return MergeAlternative(
        status_code=candidate["status_code"],
        availability=(
            bool(candidate["availability"])
            if candidate["availability"] is not None else None
        ),
        shift_code=candidate["shift_code"],
        start_time=candidate["start_time"],
        end_time=candidate["end_time"],
        station=candidate["station"],
        notes=candidate["notes"],
        source_references=[_reference(item) for item in rows],
    )


def merge_preview(
    organization_id: str,
    logical_planning_id: int,
) -> DriverShiftPlanningMergePreview:
    planning = repository.get_planning(organization_id, logical_planning_id)
    sources = repository.list_sources(organization_id, logical_planning_id)
    source_rows = repository.merge_rows(organization_id, logical_planning_id)

    transporter_identities: dict[str, set[str]] = defaultdict(set)
    for row in source_rows:
        transporter_id = str(row["transporter_id"] or "").strip().casefold()
        identity = _identity_key(row)
        if transporter_id and identity:
            transporter_identities[transporter_id].add(identity)
    conflicting_transporters = {
        value for value, identities in transporter_identities.items()
        if len(identities) > 1
    }

    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    unresolved_source_rows = 0
    for row in source_rows:
        identity = _identity_key(row)
        if row["resolved_workforce_member_id"] is None:
            unresolved_source_rows += 1
        if identity is None:
            key = ("unresolved", int(row["id"]))
        else:
            key = (identity, str(row["operational_date"]))
        groups[key].append(row)

    merged_rows: list[DriverShiftPlanningMergeRow] = []
    counters = {item.value: 0 for item in MergeClassification}
    for grouped_rows in groups.values():
        grouped_rows.sort(key=lambda item: (int(item["source_order"]), int(item["id"])))
        candidate = grouped_rows[0]
        identity = _identity_key(candidate)
        transporter_ids = {
            str(item["transporter_id"] or "").strip().casefold()
            for item in grouped_rows
            if str(item["transporter_id"] or "").strip()
        }
        alternatives: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
        for item in grouped_rows:
            alternatives[_operational_values(item)].append(item)

        if transporter_ids & conflicting_transporters:
            classification = MergeClassification.IDENTITY_CONFLICT
        elif identity is None:
            classification = MergeClassification.UNRESOLVED_IDENTITY
        elif len(alternatives) > 1:
            classification = MergeClassification.POTENTIAL_CONFLICT
        elif len(grouped_rows) > 1:
            classification = MergeClassification.EXACT_DUPLICATE
        else:
            classification = MergeClassification.DISTINCT_ASSIGNMENT
        counters[classification.value] += 1

        merged_rows.append(DriverShiftPlanningMergeRow(
            identity_key=identity,
            workforce_member_id=(
                int(candidate["resolved_workforce_member_id"])
                if candidate["resolved_workforce_member_id"] is not None else None
            ),
            source_external_identifier=candidate["source_external_identifier"],
            display_name=candidate["driver_display_name"],
            operational_date=str(candidate["operational_date"]),
            status_code=candidate["status_code"],
            availability=(
                bool(candidate["availability"])
                if candidate["availability"] is not None else None
            ),
            shift_code=candidate["shift_code"],
            start_time=candidate["start_time"],
            end_time=candidate["end_time"],
            station=candidate["station"],
            transporter_id=candidate["transporter_id"],
            classification=classification,
            source_references=[_reference(item) for item in grouped_rows],
            conflicting_alternatives=(
                [_alternative(items) for items in alternatives.values()]
                if len(alternatives) > 1 else []
            ),
        ))

    return DriverShiftPlanningMergePreview(
        planning=planning,
        sources=sources,
        summary=DriverShiftPlanningMergeSummary(
            total_source_rows=len(source_rows),
            distinct_rows=counters[MergeClassification.DISTINCT_ASSIGNMENT.value],
            exact_duplicates=counters[MergeClassification.EXACT_DUPLICATE.value],
            potential_conflicts=counters[MergeClassification.POTENTIAL_CONFLICT.value],
            identity_conflicts=len(conflicting_transporters),
            unresolved_rows=unresolved_source_rows,
        ),
        rows=merged_rows,
    )


def list_identity_rows_for_logical_planning(
    organization_id: str,
    logical_planning_id: int,
) -> list[dict[str, object]]:
    return repository.list_identity_rows_for_logical_planning(
        organization_id, logical_planning_id
    )


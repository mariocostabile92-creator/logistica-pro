from collections import defaultdict
from datetime import date
import hashlib
import json

from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningError,
    DriverShiftPlanningConflictError,
    DriverShiftPlanningPublication,
    DriverShiftPlanningPublishBlockedError,
    DriverShiftPlanningResolution,
    DriverShiftPlanningResolutionType,
    DriverShiftPlanningMergePreview,
    DriverShiftPlanningMergeRow,
    DriverShiftPlanningMergeSummary,
    DriverShiftPlanningSource,
    DriverShiftPlanningSourceNotFoundError,
    DriverShiftPlanningSourceStatus,
    MergeAlternative,
    MergeClassification,
    MergeSourceReference,
    DriverShiftPlanningList,
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


def get_driver_shift_planning(
    organization_id: str,
    logical_planning_id: int,
) -> DriverShiftPlanning:
    return repository.get_planning(organization_id, logical_planning_id)


def list_driver_shift_plannings(
    organization_id: str,
) -> DriverShiftPlanningList:
    items = repository.list_plannings(organization_id)
    return DriverShiftPlanningList(
        items=items,
        current=items[0] if items else None,
    )


def current_driver_shift_planning(
    organization_id: str,
) -> DriverShiftPlanning | None:
    return list_driver_shift_plannings(organization_id).current


def resolve_import_reference(
    organization_id: str,
    fingerprint: str,
) -> dict[str, object]:
    normalized = fingerprint.strip()
    if not normalized:
        raise DriverShiftPlanningSourceNotFoundError(
            "Fingerprint import non valido."
        )
    reference = repository.import_reference_by_fingerprint(
        organization_id,
        normalized,
    )
    if reference is None:
        raise DriverShiftPlanningSourceNotFoundError(
            "Workforce import non trovato nella stessa organizzazione."
        )
    return reference


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
            "status_code", "availability", "shift_code", "operational_activity", "start_time",
            "end_time", "station", "notes",
        )
    )


def _reference(row: dict[str, object]) -> MergeSourceReference:
    return MergeSourceReference(
        source_row_id=int(row["id"]),
        workforce_import_id=int(row["workforce_import_id"]),
        filename=str(row["source_filename"]),
        sheet=str(row["source_sheet"]),
        row_number=int(row["source_row_number"]),
        source_record_key=str(row["source_record_key"]),
        source_order=int(row["source_order"]),
    )


def _preview_fingerprint(planning: DriverShiftPlanning, rows: list[dict[str, object]]) -> str:
    payload = {
        "planning_id": planning.id,
        "version": planning.version,
        "period_start": planning.period_start,
        "period_end": planning.period_end,
        "rows": [
            {key: row.get(key) for key in (
                "id", "workforce_import_id", "source_record_key",
                "resolved_workforce_member_id", "source_external_identifier",
                "transporter_id", "operational_date", "status_code", "availability",
                "shift_code", "operational_activity", "start_time", "end_time", "station", "notes",
            )}
            for row in rows
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _conflict_key(classification: MergeClassification, rows: list[dict[str, object]]) -> str:
    payload = f"{classification.value}|{','.join(str(int(row['id'])) for row in rows)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _alternative(
    rows: list[dict[str, object]],
) -> MergeAlternative:
    candidate = rows[0]
    return MergeAlternative(
        source_external_identifier=candidate["source_external_identifier"],
        driver_display_name=candidate["driver_display_name"],
        transporter_id=candidate["transporter_id"],
        status_code=candidate["status_code"],
        availability=(
            bool(candidate["availability"])
            if candidate["availability"] is not None else None
        ),
        shift_code=candidate["shift_code"],
        operational_activity=candidate["operational_activity"],
        start_time=candidate["start_time"],
        end_time=candidate["end_time"],
        station=candidate["station"],
        notes=candidate["notes"],
        source_references=[_reference(item) for item in rows],
    )


def merge_preview(
    organization_id: str,
    logical_planning_id: int,
    *,
    classification: MergeClassification | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> DriverShiftPlanningMergePreview:
    if offset < 0:
        raise DriverShiftPlanningError("offset non può essere negativo.")
    if limit is not None and not 1 <= limit <= 200:
        raise DriverShiftPlanningError("limit deve essere compreso tra 1 e 200.")
    planning = repository.get_planning(organization_id, logical_planning_id)
    sources = repository.list_sources(organization_id, logical_planning_id)
    source_rows = repository.merge_rows(organization_id, logical_planning_id)

    transporter_identities: dict[str, set[str]] = defaultdict(set)
    transporter_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        transporter_id = str(row["transporter_id"] or "").strip().casefold()
        identity = _identity_key(row)
        if transporter_id and identity:
            transporter_identities[transporter_id].add(identity)
            transporter_rows[transporter_id].append(row)
    conflicting_transporters = {
        value for value, identities in transporter_identities.items()
        if len(identities) > 1
    }

    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        identity = _identity_key(row)
        transporter = str(row["transporter_id"] or "").strip().casefold()
        operational_date = str(row["operational_date"])
        if transporter and transporter in conflicting_transporters:
            key = ("identity_conflict", transporter, operational_date)
        elif row["resolved_workforce_member_id"] is None:
            key = ("unresolved", int(row["id"]), operational_date)
        else:
            key = (identity, operational_date)
        groups[key].append(row)

    merged_rows: list[DriverShiftPlanningMergeRow] = []
    counters = {item.value: 0 for item in MergeClassification}
    resolutions = {
        item.conflict_key: item
        for item in repository.list_resolutions(
            organization_id, logical_planning_id, planning.version
        )
    }
    resolved_count = 0
    blocker_count = 0
    unresolved_identity_blockers = 0
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
            row_classification = MergeClassification.IDENTITY_CONFLICT
        elif candidate["resolved_workforce_member_id"] is None:
            row_classification = MergeClassification.UNRESOLVED_IDENTITY
        elif len(alternatives) > 1:
            row_classification = MergeClassification.POTENTIAL_CONFLICT
        elif len(grouped_rows) > 1:
            row_classification = MergeClassification.EXACT_DUPLICATE
        else:
            row_classification = MergeClassification.DISTINCT_ASSIGNMENT
        counters[row_classification.value] += 1

        identity_conflict_rows: list[dict[str, object]] = []
        if row_classification == MergeClassification.IDENTITY_CONFLICT:
            identity_conflict_rows = list(grouped_rows)

        key = _conflict_key(row_classification, grouped_rows)
        resolution = resolutions.get(key)
        requires_resolution = row_classification in {
            MergeClassification.POTENTIAL_CONFLICT,
            MergeClassification.IDENTITY_CONFLICT,
            MergeClassification.UNRESOLVED_IDENTITY,
        }
        is_resolved = bool(resolution) if requires_resolution else True
        if requires_resolution:
            if is_resolved:
                resolved_count += 1
            else:
                blocker_count += 1
                if row_classification == MergeClassification.UNRESOLVED_IDENTITY:
                    unresolved_identity_blockers += 1

        merged_rows.append(DriverShiftPlanningMergeRow(
            conflict_key=key,
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
            operational_activity=candidate["operational_activity"],
            start_time=candidate["start_time"],
            end_time=candidate["end_time"],
            station=candidate["station"],
            transporter_id=candidate["transporter_id"],
            classification=row_classification,
            source_references=[_reference(item) for item in grouped_rows],
            conflicting_alternatives=(
                [_alternative(items) for items in alternatives.values()]
                if len(alternatives) > 1 else []
            ) if row_classification != MergeClassification.IDENTITY_CONFLICT else [
                _alternative([item]) for item in identity_conflict_rows
            ],
            resolution=resolution,
            resolved=is_resolved,
        ))

    requested_classification = classification
    normalized_search = " ".join((search or "").split()).casefold()
    filtered = [
        row for row in merged_rows
        if (
            requested_classification is None
            or row.classification == requested_classification
        )
        and (
            not normalized_search
            or normalized_search in " ".join(filter(None, (
                row.display_name,
                row.source_external_identifier,
                row.transporter_id,
            ))).casefold()
        )
    ]
    paginated = filtered[offset:] if limit is None else filtered[offset:offset + limit]

    return DriverShiftPlanningMergePreview(
        planning=planning,
        sources=sources,
        summary=DriverShiftPlanningMergeSummary(
            total_source_rows=len(source_rows),
            unified_rows=len(merged_rows),
            distinct_rows=counters[MergeClassification.DISTINCT_ASSIGNMENT.value],
            exact_duplicates=counters[MergeClassification.EXACT_DUPLICATE.value],
            potential_conflicts=counters[MergeClassification.POTENTIAL_CONFLICT.value],
            identity_conflicts=len(conflicting_transporters),
            unresolved_rows=counters[MergeClassification.UNRESOLVED_IDENTITY.value],
            conflicts_to_resolve=blocker_count,
            conflicts_resolved=resolved_count,
            unresolved_identities=unresolved_identity_blockers,
            ready_to_publish=bool(sources) and blocker_count == 0 and bool(merged_rows),
        ),
        rows=paginated,
        filtered_rows=len(filtered),
        offset=offset,
        limit=limit,
        has_more=(offset + len(paginated)) < len(filtered),
        preview_fingerprint=_preview_fingerprint(planning, source_rows),
    )


def list_identity_rows_for_logical_planning(
    organization_id: str,
    logical_planning_id: int,
) -> list[dict[str, object]]:
    return repository.list_identity_rows_for_logical_planning(
        organization_id, logical_planning_id
    )


def resolve_conflict(
    organization_id: str,
    logical_planning_id: int,
    conflict_key: str,
    resolution_type: DriverShiftPlanningResolutionType,
    expected_version: int,
    *,
    selected_source_row_id: int | None = None,
    workforce_member_id: int | None = None,
    actor: str = "local_operator",
) -> DriverShiftPlanningResolution:
    planning = repository.get_planning(organization_id, logical_planning_id)
    if planning.version != expected_version:
        raise DriverShiftPlanningConflictError("Il planning è cambiato: ricarica la preview.")
    preview = merge_preview(organization_id, logical_planning_id, limit=None)
    row = next((item for item in preview.rows if item.conflict_key == conflict_key), None)
    if row is None or row.classification not in {
        MergeClassification.POTENTIAL_CONFLICT,
        MergeClassification.IDENTITY_CONFLICT,
        MergeClassification.UNRESOLVED_IDENTITY,
    }:
        raise DriverShiftPlanningError("Conflitto non valido per questa versione del planning.")
    allowed_row_ids = {reference.source_row_id for reference in row.source_references}
    resolved_payload: dict[str, object] | None = None
    if resolution_type == DriverShiftPlanningResolutionType.USE_SOURCE_ROW:
        if selected_source_row_id not in allowed_row_ids:
            raise DriverShiftPlanningError("La riga sorgente selezionata non appartiene al conflitto.")
        if row.classification == MergeClassification.UNRESOLVED_IDENTITY:
            if not workforce_member_id or not repository.workforce_member_exists(
                organization_id, workforce_member_id
            ):
                raise DriverShiftPlanningError("Seleziona un membro Workforce valido.")
            resolved_payload = {"workforce_member_id": workforce_member_id}
    elif resolution_type == DriverShiftPlanningResolutionType.EXCLUDE:
        selected_source_row_id = None
        workforce_member_id = None
    else:
        raise DriverShiftPlanningError("Tipo di risoluzione non supportato.")
    return repository.upsert_resolution(
        organization_id, logical_planning_id, expected_version, conflict_key,
        resolution_type.value, selected_source_row_id, resolved_payload,
        actor.strip() or "local_operator",
    )


def _projection_from_preview(
    organization_id: str,
    logical_planning_id: int,
    preview: DriverShiftPlanningMergePreview,
) -> list[dict[str, object]]:
    raw_rows = {
        int(row["id"]): row
        for row in repository.merge_rows(organization_id, logical_planning_id)
    }
    candidate_member_ids = {
        int(row["resolved_workforce_member_id"])
        for row in raw_rows.values()
        if row["resolved_workforce_member_id"] is not None
    }
    candidate_member_ids.update(
        int(item.resolution.resolved_payload["workforce_member_id"])
        for item in preview.rows
        if item.resolution and item.resolution.resolved_payload
        and item.resolution.resolved_payload.get("workforce_member_id") is not None
    )
    valid_member_ids = repository.valid_workforce_member_ids(
        organization_id, candidate_member_ids
    )
    projection: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()
    for merged in preview.rows:
        resolution = merged.resolution
        if resolution and resolution.resolution_type == DriverShiftPlanningResolutionType.EXCLUDE:
            continue
        if merged.classification in {
            MergeClassification.POTENTIAL_CONFLICT,
            MergeClassification.IDENTITY_CONFLICT,
            MergeClassification.UNRESOLVED_IDENTITY,
        } and resolution is None:
            raise DriverShiftPlanningPublishBlockedError("Esistono conflitti non risolti.")
        selected_row_id = (
            resolution.selected_source_row_id
            if resolution and resolution.selected_source_row_id is not None
            else merged.source_references[0].source_row_id
        )
        raw = raw_rows.get(selected_row_id)
        if raw is None:
            raise DriverShiftPlanningConflictError("Una riga sorgente non è più disponibile.")
        member_id = (
            int(resolution.resolved_payload["workforce_member_id"])
            if resolution and resolution.resolved_payload
            and resolution.resolved_payload.get("workforce_member_id") is not None
            else (
                int(raw["resolved_workforce_member_id"])
                if raw["resolved_workforce_member_id"] is not None else None
            )
        )
        if member_id is None or member_id not in valid_member_ids:
            raise DriverShiftPlanningPublishBlockedError("Una identità Workforce non è risolta.")
        operational_date = str(raw["operational_date"])
        canonical_key = (member_id, operational_date)
        if canonical_key in seen:
            raise DriverShiftPlanningPublishBlockedError(
                "Più righe produrrebbero lo stesso driver nella stessa giornata."
            )
        seen.add(canonical_key)
        status_code = str(raw["status_code"] or raw["shift_code"] or "scheduled")
        availability = (
            bool(raw["availability"])
            if raw["availability"] is not None
            else status_code.casefold() not in {"rest", "holiday", "sick", "leave", "unavailable"}
        )
        projection.append({
            "workforce_member_id": member_id,
            "operational_date": operational_date,
            "status_code": status_code,
            "availability": availability,
            "shift_code": raw["shift_code"],
            "operational_activity": raw["operational_activity"],
            "start_time": raw["start_time"],
            "end_time": raw["end_time"],
            "station": raw["station"],
            "notes": raw["notes"],
            "transporter_id": raw["transporter_id"],
            "provenance_summary": [item.model_dump() for item in merged.source_references],
            "selected_source_row_id": selected_row_id,
        })
    return projection


def publish_driver_shift_planning(
    organization_id: str,
    logical_planning_id: int,
    expected_version: int,
    expected_preview_fingerprint: str,
    *,
    actor: str = "local_operator",
) -> DriverShiftPlanningPublication:
    planning = repository.get_planning(organization_id, logical_planning_id)
    if planning.version != expected_version:
        raise DriverShiftPlanningConflictError("Il planning è cambiato: ricarica la preview.")
    if planning.status != "DRAFT":
        raise DriverShiftPlanningError("Può essere pubblicato solo un planning DRAFT.")
    preview = merge_preview(organization_id, logical_planning_id, limit=None)
    if preview.preview_fingerprint != expected_preview_fingerprint:
        raise DriverShiftPlanningConflictError("La preview è cambiata: ricaricala prima di pubblicare.")
    if not preview.sources or not any(source.status == "AVAILABLE" for source in preview.sources):
        raise DriverShiftPlanningPublishBlockedError("Collega almeno una fonte mergeabile.")
    if not preview.summary.ready_to_publish:
        raise DriverShiftPlanningPublishBlockedError("Risolvi tutti i conflitti prima di pubblicare.")
    projection = _projection_from_preview(
        organization_id, logical_planning_id, preview
    )
    if not projection:
        raise DriverShiftPlanningPublishBlockedError("La proiezione pubblicata non può essere vuota.")
    return repository.publish_projection(
        organization_id, logical_planning_id, expected_version,
        expected_preview_fingerprint, preview.preview_fingerprint,
        projection, actor.strip() or "local_operator",
    )


def create_new_revision(
    organization_id: str,
    logical_planning_id: int,
    *,
    actor: str = "local_operator",
) -> DriverShiftPlanning:
    return repository.create_revision(
        organization_id, logical_planning_id, actor.strip() or "local_operator"
    )

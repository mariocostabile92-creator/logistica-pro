from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json

from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    ImportedDailyCoverageRequirement,
)
from app.plugins.workforce.domain.legacy_coverage_backfill import (
    LegacyCoverageBackfillPreview,
    LegacyCoverageBackfillResult,
    LegacyCoverageBackfillStatus,
)
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import (
    legacy_coverage_backfill_repository as repository,
)


BACKFILL_SOURCE = CoverageSource.LEGACY_IMPORT_BACKFILL.value


class LegacyCoverageBackfillError(ValueError):
    pass


class LegacyCoverageBackfillConflictError(LegacyCoverageBackfillError):
    pass


def _requirements(
    parsed,
    workforce_import_id: int,
) -> list[ImportedDailyCoverageRequirement]:
    source_identity = (
        f"legacy-backfill:import:{workforce_import_id}:{parsed.fingerprint}"
    )
    unique: dict[tuple[str, str, str, str], ImportedDailyCoverageRequirement] = {}
    for item in parsed.coverage_requirements:
        key = (
            item.operational_date,
            str(item.station or "").strip().casefold(),
            item.operational_cycle,
            str(item.coverage_segment or "").strip().upper(),
        )
        candidate = replace(
            item,
            source=BACKFILL_SOURCE,
            source_identity=source_identity,
        )
        prior = unique.get(key)
        if prior is not None and prior != candidate:
            raise LegacyCoverageBackfillError(
                "La sorgente contiene forecast duplicati e non coerenti."
            )
        unique[key] = candidate
    return list(unique.values())


def _preview_fingerprint(
    import_record: dict[str, object],
    requirements: list[ImportedDailyCoverageRequirement],
) -> str:
    payload = {
        "workforce_import_id": import_record["workforce_import_id"],
        "fingerprint": import_record["fingerprint"],
        "requirements": [
            {
                "date": item.operational_date,
                "cycle": item.operational_cycle,
                "segment": item.coverage_segment,
                "forecast": item.forecast_routes,
                "reserve": item.reserve_percentage,
                "required": item.required_capacity,
                "reference": item.source_reference,
            }
            for item in requirements
        ],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _base_preview(
    status: LegacyCoverageBackfillStatus,
    import_record: dict[str, object] | None,
    action_required: str,
) -> LegacyCoverageBackfillPreview:
    return LegacyCoverageBackfillPreview(
        status=status,
        workforce_import_id=(
            int(import_record["workforce_import_id"]) if import_record else None
        ),
        original_filename=(str(import_record["original_filename"]) if import_record else None),
        import_fingerprint=(str(import_record["fingerprint"]) if import_record else None),
        imported_at=(str(import_record["imported_at"]) if import_record else None),
        action_required=action_required,
    )


def inspect(
    organization_id: str,
    *,
    content: bytes | None = None,
    filename: str | None = None,
    workforce_import_id: int | None = None,
) -> tuple[LegacyCoverageBackfillPreview, list[ImportedDailyCoverageRequirement]]:
    import_record = repository.find_import(
        organization_id,
        workforce_import_id=workforce_import_id,
    )
    if import_record is None:
        return _base_preview(
            LegacyCoverageBackfillStatus.NO_ELIGIBLE_IMPORT,
            None,
            "Nessun import legacy eleggibile appartiene all'organizzazione.",
        ), []
    import_summary = import_record.get("summary")
    if (
        isinstance(import_summary, dict)
        and "coverage_requirements_detected" in import_summary
    ):
        return _base_preview(
            LegacyCoverageBackfillStatus.NO_ELIGIBLE_IMPORT,
            import_record,
            "L'import selezionato non e legacy e non richiede questo backfill.",
        ), []
    if content is None:
        return _base_preview(
            LegacyCoverageBackfillStatus.SOURCE_NOT_RECOVERABLE,
            import_record,
            "Caricare il workbook originale con fingerprint corrispondente.",
        ), []
    actual_fingerprint = sha256(content).hexdigest()
    if actual_fingerprint != import_record["fingerprint"]:
        return _base_preview(
            LegacyCoverageBackfillStatus.SOURCE_MISMATCH,
            import_record,
            "Il file caricato non corrisponde all'import legacy selezionato.",
        ).model_copy(update={"source_filename": filename}), []
    parsed = interpret_workforce_workbook(content, filename or "workforce.xlsx")
    requirements = _requirements(
        parsed,
        int(import_record["workforce_import_id"]),
    )
    if not requirements:
        return _base_preview(
            LegacyCoverageBackfillStatus.SOURCE_NOT_RECOVERABLE,
            import_record,
            "La sorgente verificata non contiene forecast strutturabile.",
        ).model_copy(update={"source_filename": filename}), []
    existing = repository.existing_rows(organization_id, requirements)
    counts = Counter(
        (item.operational_cycle, item.coverage_segment) for item in requirements
    )
    source_identity = requirements[0].source_identity
    modern = sum(
        row["source_identity"] != source_identity for row in existing.values()
    )
    missing = len(requirements) - len(existing)
    status = (
        LegacyCoverageBackfillStatus.READY
        if missing else LegacyCoverageBackfillStatus.ALREADY_COMPLETE
    )
    dates = sorted(item.operational_date for item in requirements)
    preview = LegacyCoverageBackfillPreview(
        status=status,
        workforce_import_id=int(import_record["workforce_import_id"]),
        original_filename=str(import_record["original_filename"]),
        import_fingerprint=str(import_record["fingerprint"]),
        imported_at=str(import_record["imported_at"]),
        source_recoverable=True,
        source_filename=filename,
        period_start=dates[0],
        period_end=dates[-1],
        next_day_count=counts[("NEXT_DAY", None)],
        same_day_a_count=counts[("SAME_DAY", "A")],
        same_day_b_c_count=counts[("SAME_DAY", "B_C")],
        requirements_expected=len(requirements),
        existing_rows=len(existing),
        existing_modern_rows=modern,
        requirements_missing=missing,
        preview_fingerprint=_preview_fingerprint(import_record, requirements),
        action_required=(
            "Confermare il backfill dei soli bucket mancanti."
            if missing else "Nessuna scrittura necessaria."
        ),
    )
    return preview, requirements


def preview(
    organization_id: str,
    *,
    content: bytes | None = None,
    filename: str | None = None,
    workforce_import_id: int | None = None,
) -> LegacyCoverageBackfillPreview:
    result, _ = inspect(
        organization_id,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
    )
    return result


def apply(
    organization_id: str,
    *,
    content: bytes,
    filename: str,
    workforce_import_id: int,
    expected_preview_fingerprint: str,
) -> LegacyCoverageBackfillResult:
    inspection, requirements = inspect(
        organization_id,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
    )
    if inspection.status not in {
        LegacyCoverageBackfillStatus.READY,
        LegacyCoverageBackfillStatus.ALREADY_COMPLETE,
    }:
        raise LegacyCoverageBackfillError(inspection.action_required)
    if inspection.preview_fingerprint != expected_preview_fingerprint:
        raise LegacyCoverageBackfillConflictError(
            "La preview non corrisponde piu alla sorgente selezionata."
        )
    created, skipped = repository.apply_missing(organization_id, requirements)
    final, _ = inspect(
        organization_id,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
    )
    return LegacyCoverageBackfillResult(
        **final.model_dump(),
        requirements_created=created,
        requirements_skipped=skipped,
        idempotent=created == 0,
    )

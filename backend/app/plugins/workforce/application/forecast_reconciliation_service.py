from collections import Counter
from hashlib import sha256
import json

from app.plugins.workforce.application.legacy_coverage_backfill_service import (
    _requirements,
)
from app.plugins.workforce.domain.coverage import ForecastAuthorityStatus
from app.plugins.workforce.domain.forecast_reconciliation import (
    ForecastReconciliationPreview,
    ForecastReconciliationResult,
    ForecastReconciliationStatus,
)
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import (
    forecast_reconciliation_repository as repository,
    legacy_coverage_backfill_repository,
)


class ForecastReconciliationError(ValueError):
    pass


class ForecastReconciliationConflictError(ForecastReconciliationError):
    pass


def _logical_key(item) -> tuple[str, str, str, str]:
    return (
        item.operational_date,
        str(item.station or "").strip().casefold(),
        item.operational_cycle,
        str(item.coverage_segment or "").strip().upper(),
    )


def _base(
    status: ForecastReconciliationStatus,
    record: dict[str, object] | None,
    action: str,
) -> ForecastReconciliationPreview:
    return ForecastReconciliationPreview(
        status=status,
        workforce_import_id=(int(record["workforce_import_id"]) if record else None),
        original_filename=(str(record["original_filename"]) if record else None),
        import_fingerprint=(str(record["fingerprint"]) if record else None),
        action_required=action,
    )


def _inspect(
    organization_id: str,
    *,
    actor: str,
    content: bytes,
    filename: str,
    workforce_import_id: int,
    audit: bool,
) -> tuple[ForecastReconciliationPreview, list, str | None]:
    record = legacy_coverage_backfill_repository.find_import(
        organization_id,
        workforce_import_id=workforce_import_id,
    )
    if record is None:
        return _base(
            ForecastReconciliationStatus.NO_ELIGIBLE_IMPORT,
            None,
            "Nessun import legacy eleggibile appartiene all'organizzazione.",
        ), [], None
    actual_fingerprint = sha256(content).hexdigest()
    if actual_fingerprint != record["fingerprint"]:
        return _base(
            ForecastReconciliationStatus.SOURCE_MISMATCH,
            record,
            "Il file caricato non corrisponde all'import legacy selezionato.",
        ).model_copy(update={"source_filename": filename}), [], None

    parsed = interpret_workforce_workbook(content, filename)
    requirements = _requirements(parsed, workforce_import_id)
    rejected = [
        item for item in requirements
        if item.authority_status == ForecastAuthorityStatus.REJECTED_TEMPLATE.value
    ]
    suspects = [
        item for item in requirements
        if item.authority_status == ForecastAuthorityStatus.SUSPECT_TEMPLATE.value
    ]
    if not rejected:
        return _base(
            ForecastReconciliationStatus.SOURCE_NOT_RECOVERABLE,
            record,
            "La sorgente verificata non contiene template forecast da riconciliare.",
        ).model_copy(update={"source_filename": filename}), [], None

    source_identity = requirements[0].source_identity
    matched = repository.matching_rows(
        organization_id,
        source_identity,
        [*rejected, *suspects],
    )
    manual_rows = repository.manual_override_rows(organization_id, rejected)
    manual_keys = set(manual_rows)
    rejected_keys = {_logical_key(item): item for item in rejected}
    suspect_keys = {_logical_key(item) for item in suspects}
    rejected_matched = {
        key: row for key, row in matched.items() if key in rejected_keys
    }
    suspect_matched = {
        key: row for key, row in matched.items() if key in suspect_keys
    }
    pending_keys = {
        key
        for key, row in rejected_matched.items()
        if (
            row["authority_status"]
            != ForecastAuthorityStatus.REJECTED_TEMPLATE.value
            or row["detection_reason"] != rejected_keys[key].detection_reason
        )
    }
    counts = Counter((item.operational_cycle, item.coverage_segment) for item in suspects)
    dates = sorted(item.operational_date for item in [*rejected, *suspects])
    effective_before = (
        len(suspect_matched)
        + len(pending_keys)
        + len(manual_keys - pending_keys)
    )
    effective_after = len(suspect_matched) + len(manual_keys)
    fingerprint_payload = {
        "organization_id": organization_id,
        "workforce_import_id": workforce_import_id,
        "import_fingerprint": record["fingerprint"],
        "target_rows": sorted(
            (
                int(row["id"]),
                *key,
                int(row["forecast_routes"]),
                row["source_reference"],
            )
            for key, row in matched.items()
        ),
        "manual_rows": sorted(
            (
                int(row["id"]),
                *key,
                int(row["forecast_routes"]),
                row["source_identity"],
                row["updated_at"],
            )
            for key, row in manual_rows.items()
        ),
    }
    preview_fingerprint = sha256(
        json.dumps(
            fingerprint_payload, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    status = (
        ForecastReconciliationStatus.READY
        if pending_keys
        else ForecastReconciliationStatus.ALREADY_COMPLETE
    )
    result = ForecastReconciliationPreview(
        status=status,
        workforce_import_id=workforce_import_id,
        original_filename=str(record["original_filename"]),
        import_fingerprint=str(record["fingerprint"]),
        source_filename=filename,
        period_start=dates[0],
        period_end=dates[-1],
        next_day_affected=len(rejected_matched),
        same_day_a_suspect=counts[("SAME_DAY", "A")],
        same_day_b_c_suspect=counts[("SAME_DAY", "B_C")],
        persisted_rows_matched=len(matched),
        manual_overrides_preserved=len(manual_keys),
        effective_rows_before=effective_before,
        effective_rows_after=effective_after,
        rows_pending=len(pending_keys),
        rows_reconciled=len(rejected_matched) - len(pending_keys),
        preview_fingerprint=preview_fingerprint,
        action_required=(
            "Confermare una sola reconciliation con questo fingerprint."
            if pending_keys
            else "Nessuna scrittura necessaria: reconciliation gia completata."
        ),
    )
    if audit:
        repository.audit_preview(
            organization_id,
            actor=actor,
            after={
                "workforce_import_id": workforce_import_id,
                "import_fingerprint": record["fingerprint"],
                "preview_fingerprint": preview_fingerprint,
                "next_day_affected": result.next_day_affected,
                "same_day_a_suspect": result.same_day_a_suspect,
                "same_day_b_c_suspect": result.same_day_b_c_suspect,
                "manual_overrides_preserved": result.manual_overrides_preserved,
                "rows_pending": result.rows_pending,
            },
        )
    return result, rejected, source_identity


def preview(
    organization_id: str,
    *,
    actor: str,
    content: bytes,
    filename: str,
    workforce_import_id: int,
) -> ForecastReconciliationPreview:
    result, _, _ = _inspect(
        organization_id,
        actor=actor,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
        audit=True,
    )
    return result


def apply(
    organization_id: str,
    *,
    actor: str,
    content: bytes,
    filename: str,
    workforce_import_id: int,
    expected_preview_fingerprint: str,
) -> ForecastReconciliationResult:
    inspection, rejected, source_identity = _inspect(
        organization_id,
        actor=actor,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
        audit=False,
    )
    if inspection.status not in {
        ForecastReconciliationStatus.READY,
        ForecastReconciliationStatus.ALREADY_COMPLETE,
    }:
        raise ForecastReconciliationError(inspection.action_required)
    if inspection.preview_fingerprint != expected_preview_fingerprint:
        raise ForecastReconciliationConflictError(
            "La preview non corrisponde piu allo stato Coverage corrente."
        )
    if source_identity is None:
        raise ForecastReconciliationError(
            "La sorgente legacy non e disponibile per la reconciliation."
        )
    updated, unchanged = repository.apply_rejected(
        organization_id,
        source_identity=source_identity,
        requirements=rejected,
        actor=actor,
        preview_fingerprint=expected_preview_fingerprint,
        workforce_import_id=workforce_import_id,
        manual_overrides_preserved=inspection.manual_overrides_preserved,
    )
    final, _, _ = _inspect(
        organization_id,
        actor=actor,
        content=content,
        filename=filename,
        workforce_import_id=workforce_import_id,
        audit=False,
    )
    return ForecastReconciliationResult(
        **final.model_dump(),
        rows_updated=updated,
        rows_unchanged=unchanged,
        idempotent=updated == 0,
    )

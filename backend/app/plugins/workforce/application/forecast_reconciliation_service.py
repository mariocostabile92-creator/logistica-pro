from collections import Counter
from hashlib import sha256
import json

from app.plugins.workforce.application.legacy_coverage_backfill_service import (
    _requirements,
)
from app.plugins.workforce.domain.coverage import ForecastAuthorityStatus
from app.plugins.workforce.domain.forecast_reconciliation import (
    ForecastReconciliationPreview,
    ForecastReconciliationStatus,
)
from app.plugins.workforce.importer.workbook_interpreter import (
    interpret_workforce_workbook,
)
from app.plugins.workforce.infrastructure import (
    forecast_reconciliation_repository as repository,
    legacy_coverage_backfill_repository,
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


def preview(
    organization_id: str,
    *,
    actor: str,
    content: bytes,
    filename: str,
    workforce_import_id: int,
) -> ForecastReconciliationPreview:
    record = legacy_coverage_backfill_repository.find_import(
        organization_id,
        workforce_import_id=workforce_import_id,
    )
    if record is None:
        return _base(
            ForecastReconciliationStatus.NO_ELIGIBLE_IMPORT,
            None,
            "Nessun import legacy eleggibile appartiene all'organizzazione.",
        )
    actual_fingerprint = sha256(content).hexdigest()
    if actual_fingerprint != record["fingerprint"]:
        return _base(
            ForecastReconciliationStatus.SOURCE_MISMATCH,
            record,
            "Il file caricato non corrisponde all'import legacy selezionato.",
        ).model_copy(update={"source_filename": filename})

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
        ).model_copy(update={"source_filename": filename})

    source_identity = requirements[0].source_identity
    matched = repository.matching_rows(
        organization_id,
        source_identity,
        [*rejected, *suspects],
    )
    manual_keys = repository.manual_override_keys(organization_id, rejected)
    counts = Counter((item.operational_cycle, item.coverage_segment) for item in suspects)
    dates = sorted(
        item.operational_date for item in [*rejected, *suspects]
    )
    rejected_matched = sum(
        1
        for item in rejected
        if (
            item.operational_date,
            str(item.station or "").strip().casefold(),
            item.operational_cycle,
            str(item.coverage_segment or "").strip().upper(),
        ) in matched
    )
    before = len(matched)
    after = len(matched) - rejected_matched + len(manual_keys)
    fingerprint_payload = {
        "organization_id": organization_id,
        "workforce_import_id": workforce_import_id,
        "import_fingerprint": record["fingerprint"],
        "next_day_affected": rejected_matched,
        "same_day_a_suspect": counts[("SAME_DAY", "A")],
        "same_day_b_c_suspect": counts[("SAME_DAY", "B_C")],
        "matched_ids": sorted(int(row["id"]) for row in matched.values()),
        "manual_override_keys": sorted(manual_keys),
    }
    preview_fingerprint = sha256(
        json.dumps(
            fingerprint_payload, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    result = ForecastReconciliationPreview(
        status=ForecastReconciliationStatus.READY,
        workforce_import_id=workforce_import_id,
        original_filename=str(record["original_filename"]),
        import_fingerprint=str(record["fingerprint"]),
        source_filename=filename,
        period_start=dates[0],
        period_end=dates[-1],
        next_day_affected=rejected_matched,
        same_day_a_suspect=counts[("SAME_DAY", "A")],
        same_day_b_c_suspect=counts[("SAME_DAY", "B_C")],
        persisted_rows_matched=len(matched),
        manual_overrides_preserved=len(manual_keys),
        effective_rows_before=before,
        effective_rows_after=after,
        preview_fingerprint=preview_fingerprint,
        action_required=(
            "Richiedere un apply separato vincolato a questo fingerprint; "
            "nessuna riga viene modificata dalla preview."
        ),
    )
    repository.audit_preview(
        organization_id,
        actor=actor,
        after={
            "workforce_import_id": workforce_import_id,
            "import_fingerprint": record["fingerprint"],
            "preview_fingerprint": preview_fingerprint,
            "next_day_affected": rejected_matched,
            "same_day_a_suspect": result.same_day_a_suspect,
            "same_day_b_c_suspect": result.same_day_b_c_suspect,
            "manual_overrides_preserved": result.manual_overrides_preserved,
        },
    )
    return result

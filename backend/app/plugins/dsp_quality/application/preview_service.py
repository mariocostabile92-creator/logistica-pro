import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.attachments import service as attachment_service
from app.core.config import MAX_UPLOAD_SIZE_BYTES, SETTINGS
from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualityScorecardAdapter,
    QualitySourceInput,
)
from app.plugins.dsp_quality.application.import_service import (
    document_from_adapter,
    ingest_quality_document,
    normalize_metrics,
    select_adapter,
    validate_import_document,
)
from app.plugins.dsp_quality.application.preview_models import (
    QualityFocusPreview,
    QualityImportAction,
    QualityImportConfirmation,
    QualityImportPreview,
    QualityMetricPreview,
    QualityPreviewCounts,
    QualityPreviewIdempotency,
    QualityPreviewIdentity,
    QualityPreviewMappingCounts,
    QualityPreviewValidation,
    QualitySectionPreview,
    QualityStandardPreview,
    QualityTransporterMappingPreview,
    QualityValidationMessage,
)
from app.plugins.dsp_quality.domain.models import QualityMappingStatus
from app.plugins.dsp_quality.infrastructure import repository
from app.plugins.dsp_quality.infrastructure.adapters import AmazonScorecardPdfAdapter


PREVIEW_TOKEN_TTL_SECONDS = 15 * 60
_TOKEN_KEY = (
    SETTINGS.secret_key.encode("utf-8")
    if SETTINGS.secret_key
    else secrets.token_bytes(32)
)
_EXPECTED_DSP_METRICS = {
    "overall_score",
    "safe_driving_fico",
    "speeding_event_rate",
    "mentor_adoption_rate",
    "vsa_compliance",
    "breach_of_contract",
    "working_hours_compliance",
    "comprehensive_audit_score",
    "customer_escalation_dpmo",
    "customer_delivery_feedback_dpmo",
    "photo_on_delivery",
    "contact_compliance",
    "delivery_completion_rate",
    "delivered_not_received_dpmo",
    "lost_on_road_dpmo",
    "delivery_success_conditions_dpmo",
    "next_day_capacity_reliability",
    "same_day_capacity_reliability",
}
_KNOWN_ROW_COUNTS = {("PROF", "DLO2", 2025, 47): 159}


class QualityPreviewError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class _PreviewBundle:
    preview: QualityImportPreview
    document: QualityImportDocument | None


def _message(code: str, message: str) -> QualityValidationMessage:
    return QualityValidationMessage(code=code, message=message)


def _validate_source(source: QualitySourceInput) -> QualitySourceInput:
    filename = Path(source.filename or "").name
    if Path(filename).suffix.casefold() != ".pdf":
        raise QualityPreviewError("In Q3 e supportato esclusivamente il formato PDF.", 415)
    if (source.media_type or "").casefold() != "application/pdf":
        raise QualityPreviewError("Il Content-Type deve essere application/pdf.", 415)
    if not source.content:
        raise QualityPreviewError("Il file PDF e vuoto.")
    if len(source.content) > MAX_UPLOAD_SIZE_BYTES:
        raise QualityPreviewError("Il file supera la dimensione massima consentita.", 413)
    if not source.content.startswith(b"%PDF"):
        raise QualityPreviewError("Il contenuto non corrisponde a un PDF.")
    return source.model_copy(update={"filename": filename})


def _encode_token(organization_id: str, fingerprint: str, action: QualityImportAction) -> str:
    payload = json.dumps(
        {
            "organization_id": organization_id,
            "fingerprint": fingerprint,
            "action": action.value,
            "expires_at": int(time.time()) + PREVIEW_TOKEN_TTL_SECONDS,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_TOKEN_KEY, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")


def _decode_token(token: str) -> dict:
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + padding)
        canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
        if not hmac.compare_digest(token, canonical):
            raise ValueError
        payload, signature = decoded[:-32], decoded[-32:]
        expected = hmac.new(_TOKEN_KEY, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(payload.decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise QualityPreviewError("Preview token non valido.", 409) from exc
    if int(claims.get("expires_at", 0)) < int(time.time()):
        raise QualityPreviewError("Preview scaduta. Eseguire nuovamente la preview.", 409)
    return claims


def _empty_preview(fingerprint: str, errors: list[QualityValidationMessage]) -> QualityImportPreview:
    return QualityImportPreview(
        valid=False,
        identity=QualityPreviewIdentity(),
        counts=QualityPreviewCounts(),
        mapping=QualityPreviewMappingCounts(),
        validation=QualityPreviewValidation(errors=errors),
        idempotency=QualityPreviewIdempotency(fingerprint=fingerprint),
    )


def _mapping_preview(
    organization_id: str,
    document: QualityImportDocument,
) -> tuple[list[QualityTransporterMappingPreview], QualityPreviewMappingCounts]:
    snapshots = repository.mapping_snapshots(
        organization_id,
        [row.transporter_external_id for row in document.transporter_rows],
    )
    result = []
    counts = {
        QualityMappingStatus.MATCHED: 0,
        QualityMappingStatus.UNMAPPED: 0,
        QualityMappingStatus.AMBIGUOUS: 0,
    }
    for row in document.transporter_rows:
        snapshot = snapshots.get(row.transporter_external_id)
        status = (
            QualityMappingStatus(snapshot["status"])
            if snapshot
            else QualityMappingStatus.UNMAPPED
        )
        counts[status] += 1
        result.append(
            QualityTransporterMappingPreview(
                transporter_external_id=row.transporter_external_id,
                status=status,
                workforce_member_id=(snapshot or {}).get("workforce_member_id"),
            )
        )
    return result, QualityPreviewMappingCounts(
        matched_transporters=counts[QualityMappingStatus.MATCHED],
        unmapped_transporters=counts[QualityMappingStatus.UNMAPPED],
        ambiguous_transporters=counts[QualityMappingStatus.AMBIGUOUS],
    )


def _build_preview(
    *,
    organization_id: str,
    source: QualitySourceInput,
    adapters: list[QualityScorecardAdapter] | None = None,
) -> _PreviewBundle:
    organization_id = organization_id.strip()
    if not organization_id:
        raise QualityPreviewError("Organization is required.")
    source = _validate_source(source)
    fingerprint = hashlib.sha256(source.content).hexdigest()
    available_adapters = adapters or [AmazonScorecardPdfAdapter()]
    try:
        adapter = select_adapter(source, available_adapters)
    except ValueError:
        return _PreviewBundle(
            _empty_preview(
                fingerprint,
                [_message("TEMPLATE_NOT_RECOGNIZED", "Template Amazon scorecard non riconosciuto.")],
            ),
            None,
        )
    template = adapter.detect_template(source)
    if not template:
        return _PreviewBundle(
            _empty_preview(
                fingerprint,
                [_message("TEMPLATE_NOT_RECOGNIZED", "Template Amazon scorecard non riconosciuto.")],
            ),
            None,
        )
    try:
        document = document_from_adapter(source, adapter)
    except ValueError as exc:
        message = str(exc)
        code = "MISSING_PERIOD" if "week or year" in message else "MISSING_IDENTITY"
        preview = _empty_preview(fingerprint, [_message(code, message)])
        preview.identity.detected_template_version = template
        return _PreviewBundle(preview, None)

    errors = []
    warnings = []
    infos = []
    identity = document.identity
    if not identity.dsp_identifier.strip():
        errors.append(_message("MISSING_DSP_IDENTIFIER", "DSP identifier assente."))
    if not identity.station.strip():
        errors.append(_message("MISSING_STATION", "Station assente."))
    identifiers = [row.transporter_external_id for row in document.transporter_rows]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        errors.append(
            _message(
                "DUPLICATE_TRANSPORTER_IDS",
                f"Transporter ID duplicati nella revisione: {', '.join(duplicates[:5])}.",
            )
        )
    try:
        definitions = validate_import_document(document)
    except ValueError as exc:
        definitions = {}
        errors.append(_message("METRIC_STRUCTURE_INCOHERENT", str(exc)))
    if len(document.dsp_metrics) < 5 or not document.transporter_rows:
        errors.append(
            _message(
                "METRIC_STRUCTURE_INCOHERENT",
                "La struttura metrica del documento non e coerente con una scorecard Amazon.",
            )
        )

    inferred = bool(getattr(adapter, "geography_is_inferred", lambda _source: False)(source))
    if inferred:
        warnings.append(
            _message(
                "GEOGRAPHY_INFERRED",
                "La geography e inferita dal nome file e non e authoritative.",
            )
        )
    missing_metrics = sorted(
        _EXPECTED_DSP_METRICS - {metric.metric_key for metric in document.dsp_metrics}
    )
    if missing_metrics:
        warnings.append(
            _message(
                "OPTIONAL_METRICS_MISSING",
                f"Metriche DSP opzionali non estratte: {', '.join(missing_metrics)}.",
            )
        )
    if any(str(metric.raw_value).strip().casefold() == "n/a" for metric in document.dsp_metrics):
        warnings.append(
            _message(
                "AMBIGUOUS_NA_VALUES",
                "Sono presenti valori N/A preservati come non disponibili.",
            )
        )
    expected_rows = _KNOWN_ROW_COUNTS.get(
        (
            identity.dsp_identifier,
            identity.station,
            identity.reported_year,
            identity.reported_week,
        )
    )
    if expected_rows is not None and len(document.transporter_rows) != expected_rows:
        warnings.append(
            _message(
                "KNOWN_FIXTURE_ROW_COUNT_MISMATCH",
                f"La fixture nota contiene {expected_rows} righe; estratte {len(document.transporter_rows)}.",
            )
        )
    if not document.standards or len(document.standards.rules) < 13:
        warnings.append(
            _message("PARTIAL_STANDARDS", "La sezione standards risulta parziale.")
        )
    if document.working_hours.section_present and not document.working_hours.exceptions:
        infos.append(
            _message(
                "WORKING_HOURS_NO_EXCEPTIONS",
                "Sezione Working Hours presente senza eccezioni.",
            )
        )

    mappings, mapping_counts = _mapping_preview(organization_id, document)
    if mapping_counts.unmapped_transporters:
        warnings.append(
            _message(
                "UNMAPPED_TRANSPORTERS",
                f"{mapping_counts.unmapped_transporters} Transporter ID non sono mappati.",
            )
        )
    if mapping_counts.ambiguous_transporters:
        warnings.append(
            _message(
                "AMBIGUOUS_TRANSPORTERS",
                f"{mapping_counts.ambiguous_transporters} Transporter ID sono ambigui.",
            )
        )

    idempotency = repository.inspect_import_action(
        organization_id=organization_id,
        source_fingerprint=fingerprint,
        source_provider=identity.source_provider,
        dsp_identifier=identity.dsp_identifier,
        station=identity.station,
        reported_year=identity.reported_year,
        reported_week=identity.reported_week,
    )
    action = QualityImportAction(idempotency["action"])
    metric_previews = []
    if definitions:
        normalized = normalize_metrics(
            document.dsp_metrics,
            definitions,
            document.revision.normalization_rule_version,
        )
        metric_previews = [
            QualityMetricPreview(
                metric_key=metric.metric_key,
                raw_value=value.raw_value,
                normalized_numeric_value=value.normalized_numeric_value,
                normalized_text_value=value.normalized_text_value,
                rating=value.rating,
                compliance_state=value.compliance_state,
                value_state=value.value_state,
            )
            for metric in document.dsp_metrics
            for value in (normalized[metric.metric_key],)
        ]
    valid = not errors
    preview = QualityImportPreview(
        valid=valid,
        preview_token=_encode_token(organization_id, fingerprint, action) if valid else None,
        identity=QualityPreviewIdentity(
            dsp_identifier=identity.dsp_identifier,
            station=identity.station,
            reported_week=identity.reported_week,
            reported_year=identity.reported_year,
            rank=document.revision.rank,
            rank_wow_declared=document.revision.rank_wow_declared,
            overall_score=(
                Decimal(str(document.revision.overall_score))
                if document.revision.overall_score is not None
                else None
            ),
            overall_standing=document.revision.overall_standing,
            raw_period_label=document.revision.raw_period_label,
            geography=identity.geography,
            geography_authoritative=not inferred and identity.geography is not None,
            detected_template_version=template,
        ),
        counts=QualityPreviewCounts(
            dsp_metrics_count=len(document.dsp_metrics),
            transporter_rows_count=len(document.transporter_rows),
            working_hours_exception_count=len(document.working_hours.exceptions),
            focus_areas_count=len(document.focus_areas),
            standards_count=len(document.standards.rules) if document.standards else 0,
        ),
        mapping=mapping_counts,
        transporter_mappings=mappings,
        dsp_metrics=metric_previews,
        section_standings=[QualitySectionPreview(**item.model_dump()) for item in document.sections],
        focus_areas=[QualityFocusPreview(**item.model_dump()) for item in document.focus_areas],
        standards=[
            QualityStandardPreview(
                metric_key=item.metric_key,
                raw_target=item.raw_target,
                raw_minimum=item.raw_minimum,
                source_page=item.source_page,
            )
            for item in (document.standards.rules if document.standards else [])
        ],
        working_hours_section_present=document.working_hours.section_present,
        validation=QualityPreviewValidation(errors=errors, warnings=warnings, infos=infos),
        idempotency=QualityPreviewIdempotency(
            fingerprint=fingerprint,
            existing_scorecard=idempotency["existing_scorecard"],
            existing_revision=idempotency["existing_revision"],
            action=action,
        ),
    )
    return _PreviewBundle(preview=preview, document=document)


def preview_scorecard_import(
    *,
    organization_id: str,
    source: QualitySourceInput,
    adapters: list[QualityScorecardAdapter] | None = None,
) -> QualityImportPreview:
    return _build_preview(
        organization_id=organization_id,
        source=source,
        adapters=adapters,
    ).preview


def confirm_scorecard_import(
    *,
    organization_id: str,
    source: QualitySourceInput,
    preview_token: str,
    imported_by: str,
    expected_action: QualityImportAction | None = None,
    adapters: list[QualityScorecardAdapter] | None = None,
) -> QualityImportConfirmation:
    bundle = _build_preview(
        organization_id=organization_id,
        source=source,
        adapters=adapters,
    )
    preview = bundle.preview
    if not preview.valid or not bundle.document or not preview.idempotency.action:
        raise QualityPreviewError("Import bloccato dagli errori di validazione.")
    claims = _decode_token(preview_token)
    action = preview.idempotency.action
    if (
        claims.get("organization_id") != organization_id
        or claims.get("fingerprint") != preview.idempotency.fingerprint
        or claims.get("action") != action.value
    ):
        raise QualityPreviewError(
            "Preview non coerente o non piu attuale. Eseguire nuovamente la preview.",
            409,
        )
    if expected_action is not None and expected_action is not action:
        raise QualityPreviewError("Expected action non coerente con la preview.", 409)

    result = ingest_quality_document(
        organization_id=organization_id,
        document=bundle.document,
        source_content=source.content,
        imported_by=imported_by,
    )
    actual_action = (
        QualityImportAction.NO_OP
        if result.idempotent
        else (
            QualityImportAction.NEW_REVISION
            if result.previous_revision_id
            else QualityImportAction.CREATE
        )
    )
    if actual_action is not action:
        raise QualityPreviewError(
            "Lo stato import e cambiato durante la conferma. Ripetere la preview.",
            409,
        )

    attachment_id = repository.revision_source_attachment_reference(
        organization_id,
        result.revision_id,
    )
    if not attachment_id:
        entity_id = repository.scorecard_attachment_entity_id(
            organization_id,
            result.scorecard_id,
        )
        attachment = attachment_service.upload(
            "quality_scorecard",
            entity_id,
            source.filename,
            source.media_type or "application/pdf",
            source.content,
            imported_by,
            "Amazon DSP scorecard source",
            organization_id,
        )
        attachment_id = attachment["id"]
        try:
            repository.set_revision_source_attachment_reference(
                organization_id,
                result.revision_id,
                attachment_id,
            )
        except Exception:
            attachment_service.delete(attachment_id, organization_id, imported_by)
            raise

    return QualityImportConfirmation(
        scorecard_id=result.scorecard_id,
        revision_id=result.revision_id,
        action=actual_action,
        idempotent=result.idempotent,
        revision_created=result.revision_created,
        previous_revision_id=result.previous_revision_id,
        active_revision_id=result.active_revision_id,
        source_attachment_reference=attachment_id,
        transporter_rows=result.transporter_rows,
        warnings=result.warnings,
    )

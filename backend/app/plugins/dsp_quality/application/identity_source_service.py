import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.config import MAX_UPLOAD_SIZE_BYTES, SETTINGS
from app.importers.workbook_profiler.models import ScannedSheet
from app.importers.workbook_profiler.workbook_scanner import scan_workbook
from app.plugins.dsp_quality.application.history_service import ensure_scorecard
from app.plugins.dsp_quality.application.identity_source_models import (
    ExactIdentityApplyResult,
    IdentityConfidenceClass,
    IdentityEvidenceStatus,
    IdentitySourceCoverage,
    IdentitySourceMetadata,
    IdentitySourcePreview,
    IdentitySourcePreviewRow,
)
from app.plugins.dsp_quality.application.import_contract import QualitySourceInput
from app.plugins.dsp_quality.application.reconciliation_service import reconciliation_state
from app.plugins.dsp_quality.infrastructure import identity_source_repository
from app.plugins.dsp_quality.infrastructure.adapters.tabular_identity_source import (
    IdentitySourceDetection,
    IdentitySourceSelection,
    detect_identity_source,
)


TOKEN_TTL_SECONDS = 15 * 60
_TOKEN_KEY = SETTINGS.secret_key.encode("utf-8") if SETTINGS.secret_key else secrets.token_bytes(32)


class IdentitySourceError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class _SourceBundle:
    filename: str
    source_type: str
    source_reference: str
    fingerprint: str
    sheets: tuple[ScannedSheet, ...]


def _normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", text)


def _encode_token(organization_id: str, scorecard_id: str, bundle: _SourceBundle, detection: IdentitySourceDetection) -> str:
    payload = json.dumps({
        "organization_id": organization_id,
        "scorecard_id": scorecard_id,
        "fingerprint": bundle.fingerprint,
        "source_reference": bundle.source_reference,
        "source_type": bundle.source_type,
        "sheet": detection.sheet,
        "transporter_column": detection.transporter_column,
        "driver_column": detection.driver_column,
        "expires_at": int(time.time()) + TOKEN_TTL_SECONDS,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_TOKEN_KEY, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")


def _decode_token(token: str) -> dict:
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload, signature = decoded[:-32], decoded[-32:]
        expected = hmac.new(_TOKEN_KEY, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(payload.decode("utf-8"))
        if int(claims["expires_at"]) < int(time.time()):
            raise IdentitySourceError("La preview e scaduta. Analizzare nuovamente la fonte.", 409)
        return claims
    except IdentitySourceError:
        raise
    except Exception as exc:
        raise IdentitySourceError("Token preview fonte non valido.", 409) from exc


def _generic_bundle(source: QualitySourceInput) -> _SourceBundle:
    filename = Path(source.filename or "").name
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".xlsx", ".csv"}:
        raise IdentitySourceError("Sono supportati soltanto file .xlsx e .csv.", 415)
    if not source.content:
        raise IdentitySourceError("Il file fonte e vuoto.")
    if len(source.content) > MAX_UPLOAD_SIZE_BYTES:
        raise IdentitySourceError("Il file supera la dimensione massima consentita.", 413)
    fingerprint = hashlib.sha256(source.content).hexdigest()
    workbook = scan_workbook(source.content, filename, preserve_formula_metadata=False)
    return _SourceBundle(
        filename=filename,
        source_type="GENERIC_FILE_EXACT",
        source_reference=f"upload:{fingerprint}",
        fingerprint=fingerprint,
        sheets=workbook.sheets,
    )


def _planning_bundle(organization_id: str) -> _SourceBundle:
    source = identity_source_repository.latest_planning_source(organization_id)
    if not source:
        raise IdentitySourceError("Nessuna fonte Planning disponibile per l'organizzazione.", 404)
    records = []
    for item in source["normalized_rows"]:
        record = dict(item.get("raw") or {})
        for key in ("workforce_member_id", "external_identifier", "driver_id"):
            if item.get(key) not in (None, "") and key not in record:
                record[key] = item[key]
        records.append(record)
    headers: list[str] = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)
    rows = [headers, *[[record.get(key) for key in headers] for record in records]]
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _SourceBundle(
        filename=source["original_filename"],
        source_type="PLANNING_EXACT",
        source_reference=f"planning-import:{source['id']}",
        fingerprint=hashlib.sha256(canonical).hexdigest(),
        sheets=(ScannedSheet(name=source["sheet_name"] or "Planning", rows=rows),),
    )


def _bundle(organization_id: str, source: QualitySourceInput | None, use_planning: bool) -> _SourceBundle:
    if source is not None:
        return _generic_bundle(source)
    if use_planning:
        return _planning_bundle(organization_id)
    raise IdentitySourceError("Caricare un file oppure scegliere la fonte Planning.")


def _metadata(bundle: _SourceBundle, detection: IdentitySourceDetection) -> IdentitySourceMetadata:
    return IdentitySourceMetadata(
        filename=bundle.filename,
        source_type=bundle.source_type,
        source_reference=bundle.source_reference,
        sheet=detection.sheet,
        header_row=detection.header_row,
        transporter_column=detection.transporter_column,
        driver_column=detection.driver_column,
        driver_identifier_kind=detection.driver_identifier_kind,
        rows_detected=len(detection.rows),
        candidate_sheets=detection.candidate_sheets,
        transporter_candidates=detection.transporter_candidates,
        driver_candidates=detection.driver_candidates,
    )


def _resolved_row(source_row, members: list[dict], evidence_source: str) -> IdentitySourcePreviewRow:
    raw = source_row.source_driver_identifier.strip()
    if not raw:
        return IdentitySourcePreviewRow(
            transporter_external_id=source_row.transporter_external_id,
            source_driver_value=None,
            confidence=IdentityConfidenceClass.UNRESOLVED,
            evidence_source=evidence_source,
            status=IdentityEvidenceStatus.UNRESOLVED,
            reason="La fonte non contiene un identificatore driver.",
            source_sheet=source_row.source_sheet,
            source_row=source_row.source_row,
        )
    if source_row.driver_identifier_kind == "workforce_member_id":
        matches = [item for item in members if str(item["id"]) == raw]
    elif source_row.driver_identifier_kind == "external_identifier":
        matches = [item for item in members if _normalized(item["external_identifier"]) == _normalized(raw)]
    else:
        matches = [item for item in members if _normalized(item["display_name"]) == _normalized(raw)]
    if not matches:
        return IdentitySourcePreviewRow(
            transporter_external_id=source_row.transporter_external_id,
            source_driver_value=raw,
            confidence=IdentityConfidenceClass.UNRESOLVED,
            evidence_source=evidence_source,
            status=IdentityEvidenceStatus.UNRESOLVED,
            reason="Nessun membro Workforce organization-scoped corrisponde alla fonte.",
            source_sheet=source_row.source_sheet,
            source_row=source_row.source_row,
        )
    if len(matches) > 1:
        return IdentitySourcePreviewRow(
            transporter_external_id=source_row.transporter_external_id,
            source_driver_value=raw,
            confidence=IdentityConfidenceClass.CONFLICT,
            evidence_source=evidence_source,
            status=IdentityEvidenceStatus.CONFLICT,
            reason="L'identita driver e ambigua nell'organizzazione.",
            source_sheet=source_row.source_sheet,
            source_row=source_row.source_row,
        )
    member = matches[0]
    deterministic = source_row.driver_identifier_kind in {"workforce_member_id", "external_identifier"}
    return IdentitySourcePreviewRow(
        transporter_external_id=source_row.transporter_external_id,
        source_driver_value=raw,
        proposed_workforce_member_id=int(member["id"]),
        proposed_display_name=member["display_name"],
        confidence=IdentityConfidenceClass.EXACT if deterministic else IdentityConfidenceClass.SUGGESTED,
        evidence_source=evidence_source if deterministic else "NAME_SUGGESTION",
        status=IdentityEvidenceStatus.EXACT if deterministic else IdentityEvidenceStatus.SUGGESTED,
        reason=(
            "Identificatore Workforce canonico risolto senza ambiguita."
            if deterministic else
            "Nome esatto e univoco: richiede conferma manuale."
        ),
        source_sheet=source_row.source_sheet,
        source_row=source_row.source_row,
    )


def preview_identity_source(
    *,
    organization_id: str,
    scorecard_id: str,
    source: QualitySourceInput | None = None,
    use_planning: bool = False,
    selection: IdentitySourceSelection | None = None,
) -> IdentitySourcePreview:
    ensure_scorecard(organization_id, scorecard_id)
    bundle = _bundle(organization_id, source, use_planning)
    detection = detect_identity_source(bundle.sheets, selection)
    metadata = _metadata(bundle, detection)
    if detection.status != "READY":
        return IdentitySourcePreview(
            valid=False,
            schema_status=detection.status,
            scorecard_id=scorecard_id,
            source=metadata,
        )

    snapshot = reconciliation_state(organization_id, scorecard_id)
    quality_rows = {row.transporter_external_id: row for row in snapshot.rows}
    members = identity_source_repository.strict_workforce_members(organization_id)
    grouped: dict[str, list] = {}
    for row in detection.rows:
        grouped.setdefault(row.transporter_external_id, []).append(row)
    preview_rows = []
    for transporter_id, quality_row in quality_rows.items():
        source_rows = grouped.get(transporter_id, [])
        unique_values = {_normalized(item.source_driver_identifier) for item in source_rows}
        if len(unique_values) > 1:
            item = source_rows[0]
            resolved = IdentitySourcePreviewRow(
                transporter_external_id=transporter_id,
                source_driver_value=" / ".join(sorted(value for value in unique_values if value)),
                confidence=IdentityConfidenceClass.CONFLICT,
                evidence_source=bundle.source_type,
                status=IdentityEvidenceStatus.CONFLICT,
                reason="Lo stesso Transporter ID e associato a driver diversi nella fonte.",
                source_sheet=item.source_sheet,
                source_row=item.source_row,
            )
        elif not source_rows:
            resolved = IdentitySourcePreviewRow(
                transporter_external_id=transporter_id,
                confidence=IdentityConfidenceClass.UNRESOLVED,
                evidence_source="NO_EVIDENCE",
                status=IdentityEvidenceStatus.UNRESOLVED,
                reason="Transporter non presente nella fonte selezionata.",
            )
        else:
            resolved = _resolved_row(source_rows[0], members, bundle.source_type)

        if quality_row.mapping_status == "MATCHED":
            if resolved.proposed_workforce_member_id and resolved.proposed_workforce_member_id != quality_row.workforce_member_id:
                resolved = resolved.model_copy(update={
                    "confidence": IdentityConfidenceClass.CONFLICT,
                    "status": IdentityEvidenceStatus.CONFLICT_WITH_VERIFIED_MAPPING,
                    "reason": "La fonte contraddice il mapping verificato esistente.",
                })
            else:
                resolved = resolved.model_copy(update={
                    "proposed_workforce_member_id": quality_row.workforce_member_id,
                    "proposed_display_name": quality_row.workforce_display_name,
                    "confidence": IdentityConfidenceClass.EXACT,
                    "evidence_source": "VERIFIED_MAPPING",
                    "status": IdentityEvidenceStatus.ALREADY_VERIFIED,
                    "reason": "Il mapping Q8 verificato ha priorita sulla nuova fonte.",
                })
        preview_rows.append(resolved)

    status_counts = {status: 0 for status in IdentityEvidenceStatus}
    for row in preview_rows:
        status_counts[row.status] += 1
    source_ids = set(grouped)
    coverage = IdentitySourceCoverage(
        quality_transporters=len(quality_rows),
        source_transporters=len(source_ids),
        exact_matches=status_counts[IdentityEvidenceStatus.EXACT],
        suggestions=status_counts[IdentityEvidenceStatus.SUGGESTED],
        unresolved=status_counts[IdentityEvidenceStatus.UNRESOLVED],
        conflicts=(
            status_counts[IdentityEvidenceStatus.CONFLICT]
            + status_counts[IdentityEvidenceStatus.CONFLICT_WITH_VERIFIED_MAPPING]
        ),
        already_verified=status_counts[IdentityEvidenceStatus.ALREADY_VERIFIED],
        source_only=len(source_ids - set(quality_rows)),
    )
    default_bucket = "suggested" if coverage.suggestions else (
        "exact" if coverage.exact_matches else (
            "conflict" if coverage.conflicts else "unresolved"
        )
    )
    return IdentitySourcePreview(
        valid=True,
        schema_status="READY",
        scorecard_id=scorecard_id,
        preview_token=_encode_token(organization_id, scorecard_id, bundle, detection),
        source=metadata,
        coverage=coverage,
        default_bucket=default_bucket,
        rows=preview_rows,
    )


def apply_exact_identity_matches(
    *,
    organization_id: str,
    scorecard_id: str,
    actor: str,
    preview_token: str,
    source: QualitySourceInput | None = None,
    use_planning: bool = False,
) -> ExactIdentityApplyResult:
    claims = _decode_token(preview_token)
    if claims.get("organization_id") != organization_id or claims.get("scorecard_id") != scorecard_id:
        raise IdentitySourceError("Preview non coerente con organizzazione o scorecard.", 409)
    selection = IdentitySourceSelection(
        sheet=claims.get("sheet"),
        transporter_column=claims.get("transporter_column"),
        driver_column=claims.get("driver_column"),
    )
    preview = preview_identity_source(
        organization_id=organization_id,
        scorecard_id=scorecard_id,
        source=source,
        use_planning=use_planning,
        selection=selection,
    )
    current_claims = _decode_token(preview.preview_token or "")
    for field in (
        "fingerprint", "source_reference", "source_type", "sheet",
        "transporter_column", "driver_column",
    ):
        if claims.get(field) != current_claims.get(field):
            raise IdentitySourceError("La fonte e cambiata dopo la preview. Analizzarla nuovamente.", 409)
    if preview.coverage.conflicts:
        raise IdentitySourceError("Risolvi i conflitti prima di applicare le corrispondenze certe.", 409)
    exact = [row for row in preview.rows if row.status is IdentityEvidenceStatus.EXACT]
    rows = [{
        "transporter_external_id": row.transporter_external_id,
        "workforce_member_id": row.proposed_workforce_member_id,
        "source_sheet": row.source_sheet,
        "source_row": row.source_row,
        "resolution_method": preview.source.driver_identifier_kind,
        "identity_id": uuid4().hex,
        "event_id": uuid4().hex,
    } for row in exact]
    try:
        result = identity_source_repository.apply_exact_mappings(
            organization_id=organization_id,
            actor=actor,
            rows=rows,
            source=preview.source.model_dump(),
        )
    except identity_source_repository.ExactIdentityConflictError as exc:
        raise IdentitySourceError(str(exc), 409) from exc
    return ExactIdentityApplyResult(
        scorecard_id=scorecard_id,
        applied=len(result["applied"]),
        already_verified=result["already_verified"] + preview.coverage.already_verified,
        mappings=result["applied"],
    )

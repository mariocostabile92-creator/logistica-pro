import hashlib

from app.plugins.dsp_quality.application.import_contract import (
    QualityImportDocument,
    QualityImportResult,
    QualityRevisionInput,
    QualityScorecardAdapter,
    QualitySourceInput,
)
from app.plugins.dsp_quality.application.normalization import (
    normalize_quality_value,
)
from app.plugins.dsp_quality.domain.models import (
    QualityMetricScope,
    QualityValueType,
)
from app.plugins.dsp_quality.infrastructure import repository


def _select_adapter(
    source: QualitySourceInput,
    adapters: list[QualityScorecardAdapter],
) -> QualityScorecardAdapter:
    supported = [adapter for adapter in adapters if adapter.supports(source)]
    if not supported:
        raise ValueError("No DSP Quality adapter supports this source.")
    if len(supported) > 1:
        raise ValueError("More than one DSP Quality adapter supports this source.")
    return supported[0]


def _document_from_adapter(
    source: QualitySourceInput,
    adapter: QualityScorecardAdapter,
) -> QualityImportDocument:
    revision = adapter.extract_revision(source)
    detected = adapter.detect_template(source)
    if detected and not revision.detected_template_version:
        revision = revision.model_copy(update={"detected_template_version": detected})
    return QualityImportDocument(
        identity=adapter.extract_identity(source),
        revision=QualityRevisionInput.model_validate(revision),
        sections=adapter.extract_section_standings(source),
        dsp_metrics=adapter.extract_dsp_metrics(source),
        transporter_rows=adapter.extract_transporter_rows(source),
        working_hours=adapter.extract_working_hour_exceptions(source),
        focus_areas=adapter.extract_focus_areas(source),
        standards=adapter.extract_standard_rules(source),
    )


def _validate_document(document: QualityImportDocument) -> dict[str, dict]:
    definitions = repository.metric_definitions()
    if not definitions:
        raise ValueError("DSP Quality metric catalog is not initialized.")

    def definition(metric_key: str, allowed: set[str]) -> dict:
        item = definitions.get(metric_key)
        if not item:
            raise ValueError(f"Unknown DSP Quality metric: {metric_key}.")
        if item["scope"] not in allowed:
            raise ValueError(
                f"Metric {metric_key} is not valid for this observation scope."
            )
        return item

    for metric in document.dsp_metrics:
        definition(metric.metric_key, {QualityMetricScope.DSP.value, QualityMetricScope.BOTH.value})
    for row in document.transporter_rows:
        keys = [metric.metric_key for metric in row.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("Transporter metric keys must be unique per row.")
        for metric in row.metrics:
            definition(metric.metric_key, {QualityMetricScope.TRANSPORTER.value, QualityMetricScope.BOTH.value})
    for focus in document.focus_areas:
        if focus.metric_key:
            definition(focus.metric_key, {QualityMetricScope.DSP.value, QualityMetricScope.BOTH.value})
    if document.standards:
        keys = [rule.metric_key for rule in document.standards.rules]
        if len(keys) != len(set(keys)):
            raise ValueError("Standard rule metric keys must be unique.")
        for rule in document.standards.rules:
            item = definition(
                rule.metric_key,
                {QualityMetricScope.DSP.value, QualityMetricScope.BOTH.value},
            )
            if item["direction"] != rule.direction.value:
                raise ValueError(f"Direction mismatch for {rule.metric_key}.")
    return definitions


def _normalize_metrics(metrics, definitions, rule_version):
    result = {}
    for metric in metrics:
        value_type = QualityValueType(definitions[metric.metric_key]["value_type"])
        result[metric.metric_key] = normalize_quality_value(
            metric.raw_value,
            value_type,
            rating=metric.rating,
            compliance_state=metric.compliance_state,
            rule_version=rule_version,
        )
    return result


def _normalize_optional_bool(raw: str | None) -> bool | None:
    if raw is None or not raw.strip():
        return None
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "y", "x", "exceeded"}:
        return True
    if normalized in {"0", "false", "no", "n", "none"}:
        return False
    return None


def ingest_quality_document(
    *,
    organization_id: str,
    document: QualityImportDocument,
    source_content: bytes,
    imported_by: str,
) -> QualityImportResult:
    organization_id = organization_id.strip()
    imported_by = imported_by.strip()
    if not organization_id or not imported_by:
        raise ValueError("Organization and importer are required.")
    if not source_content:
        raise ValueError("Source content is required for traceability.")
    definitions = _validate_document(document)
    rule_version = document.revision.normalization_rule_version
    dsp_values = _normalize_metrics(document.dsp_metrics, definitions, rule_version)
    transporter_values = [
        _normalize_metrics(row.metrics, definitions, rule_version)
        for row in document.transporter_rows
    ]
    working_hour_values = [
        {
            "daily_limit_exceeded": _normalize_optional_bool(item.daily_limit_exceeded),
            "weekly_limit_exceeded": _normalize_optional_bool(item.weekly_limit_exceeded),
            "under_offwork_limit": _normalize_optional_bool(item.under_offwork_limit),
            "work_day_limit_exceeded": _normalize_optional_bool(item.work_day_limit_exceeded),
            "wh_exception": _normalize_optional_bool(item.wh_exception),
        }
        for item in document.working_hours.exceptions
    ]
    fingerprint = hashlib.sha256(source_content).hexdigest()
    persisted = repository.persist_import(
        organization_id=organization_id,
        document=document,
        source_fingerprint=fingerprint,
        imported_by=imported_by,
        dsp_values=dsp_values,
        transporter_values=transporter_values,
        working_hour_values=working_hour_values,
    )
    return QualityImportResult(
        **persisted,
        source_fingerprint_sha256=fingerprint,
        transporter_rows=len(document.transporter_rows),
        warnings=document.warnings,
    )


def ingest_quality_source(
    *,
    organization_id: str,
    source: QualitySourceInput,
    adapters: list[QualityScorecardAdapter],
    imported_by: str,
) -> QualityImportResult:
    adapter = _select_adapter(source, adapters)
    document = _document_from_adapter(source, adapter)
    return ingest_quality_document(
        organization_id=organization_id,
        document=document,
        source_content=source.content,
        imported_by=imported_by,
    )

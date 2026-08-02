import { escapeHtml } from "../../utils/dom.js";
import { operationLabel, procedureDateParts, statusPresentation } from "./components.js";

export function liveStatusPresentation(item) {
  return statusPresentation(item.is_late ? "late" : item.status);
}

export function journalLiveCard(item, selectedId) {
  const status = liveStatusPresentation(item);
  const opened = procedureDateParts({ ...item, occurred_at: item.opened_at || item.scheduled_at || item.created_at });
  const updated = procedureDateParts({ ...item, occurred_at: item.occurred_at || item.in_progress_at || item.opened_at || item.created_at });
  return `<button type="button" class="jcr-item jcr-live-item status-${status.tone} ${selectedId === item.id ? "active" : ""}"
    data-jcr-id="${escapeHtml(item.id)}" aria-pressed="${selectedId === item.id}">
    <header><div><strong>${escapeHtml(item.declared_driver_identifier)}</strong><small>${escapeHtml(item.plate_snapshot)} · ${escapeHtml(item.vehicle_model || "Modello non registrato")}</small></div>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <dl><div><dt>Procedura</dt><dd>${escapeHtml(operationLabel(item.operation_type))}</dd></div>
      <div><dt>Ora apertura</dt><dd>${escapeHtml(opened.time)}</dd></div>
      <div><dt>Ultimo aggiornamento</dt><dd>${escapeHtml(updated.time)}</dd></div>
      <div><dt>Origine</dt><dd>${escapeHtml(item.origin)}</dd></div></dl>
    <div class="jcr-card-meta"><span>${item.anomaly_present ? "Anomalia sì" : "Anomalia no"}</span>
      <span>${item.media.length ? "Allegati sì" : "Allegati no"}</span></div>
    <span class="jcr-card-action">Apri monitoraggio <b aria-hidden="true">›</b></span>
  </button>`;
}

export function journalLiveKpis() {
  return [
    ["expected_drivers", "Driver attesi", "expected"],
    ["not_started", "Non iniziati", "generated"],
    ["in_progress_live", "In compilazione", "progress"],
    ["completed_live", "Completati", "completed"],
    ["with_anomalies", "Con anomalie", "anomaly"],
    ["late", "In ritardo", "late"],
  ].map(([key, label, tone]) => `<article class="jcr-kpi tone-${tone}">
    <strong data-jcr-kpi="${key}">0</strong><span>${label}</span><small>Giornata operativa</small></article>`).join("");
}

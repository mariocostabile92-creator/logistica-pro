import { escapeHtml } from "../../utils/dom.js";
import {
  operationLabel, procedureDateParts, statusPresentation,
} from "../journal-control-room/components.js";

export function dailyTimeline(items, selectedId) {
  if (!items.length) return `<div class="jcr-empty"><strong>Nessuna procedura</strong><p>Non ci sono registrazioni per il giorno e i filtri selezionati.</p></div>`;
  return `<ol class="gdb-daily-timeline" aria-label="Cronologia della giornata">${items.map(item => {
    const occurred = procedureDateParts(item);
    const status = statusPresentation(item.status);
    return `<li class="status-${status.tone}"><time datetime="${escapeHtml(item.occurred_at)}">${escapeHtml(occurred.time)}</time>
      <article class="${selectedId === item.id ? "active" : ""}">
        <header><div><strong>${escapeHtml(item.declared_driver_identifier)}</strong><small>${escapeHtml(operationLabel(item.operation_type))}</small></div>
          <span class="jcr-status status-${status.tone}">${escapeHtml(status.label)}</span></header>
        <dl><div><dt>Veicolo</dt><dd>${escapeHtml(item.plate_snapshot)} · ${escapeHtml(item.vehicle_model || "Modello non registrato")}</dd></div>
          <div><dt>Origine</dt><dd>${escapeHtml(item.origin)}</dd></div></dl>
        <div class="jcr-card-meta"><span>${item.anomaly_present ? "Anomalia presente" : "Nessuna anomalia"}</span><span>${item.media.length} allegati</span></div>
        <button type="button" data-jcr-id="${escapeHtml(item.id)}" aria-pressed="${selectedId === item.id}">Apri GDB</button>
      </article></li>`;
  }).join("")}</ol>`;
}

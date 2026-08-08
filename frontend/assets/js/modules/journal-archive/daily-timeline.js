import { escapeHtml } from "../../utils/dom.js";
import { operationLabel, procedureDateParts } from "../journal-control-room/components.js";
import {
  liveCardPriority, statusPresentation,
} from "../journal-control-room/live-status-presenter.js";
import { driverDisplayName } from "../journal-control-room/driver-display.js";

export function dailyTimeline(items, selectedId) {
  if (!items.length) return `<div class="jcr-empty"><strong>Nessuna procedura</strong><p>Non ci sono registrazioni per il giorno e i filtri selezionati.</p></div>`;
  return `<ol class="gdb-daily-timeline" aria-label="Cronologia della giornata">${items.map(item => {
    const occurred = procedureDateParts(item);
    const status = statusPresentation(item.status);
    const priority = liveCardPriority(item);
    return `<li class="status-${status.tone} priority-${priority.tone}">
      <time datetime="${escapeHtml(item.occurred_at)}"><strong>${escapeHtml(occurred.time)}</strong><small>${escapeHtml(occurred.date)}</small></time>
      <span class="gdb-timeline-node" aria-hidden="true"></span>
      <article class="${selectedId === item.id ? "active" : ""}">
        <header><div><strong>${escapeHtml(driverDisplayName(item))}</strong><small>${escapeHtml(item.plate_snapshot)} · ${escapeHtml(item.vehicle_model || "Modello non registrato")}</small></div>
          <span class="jcr-status status-${status.tone}">${escapeHtml(status.label)}</span></header>
        <p class="gdb-timeline-procedure">${escapeHtml(operationLabel(item.operation_type))}</p>
        <div class="gdb-timeline-signals">${item.is_late ? '<b class="signal-late">In ritardo</b>' : ""}
          ${item.anomaly_present ? '<b class="signal-anomaly">Anomalia presente</b>' : '<span>Nessuna anomalia</span>'}
          <span>${item.media.length} allegati</span></div>
        <footer><small>Origine · ${escapeHtml(item.origin)}</small>
          <button type="button" data-jcr-id="${escapeHtml(item.id)}" aria-pressed="${selectedId === item.id}">Apri GDB</button></footer>
      </article></li>`;
  }).join("")}</ol>`;
}

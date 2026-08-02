import { escapeHtml } from "../../utils/dom.js";
import { completionStatus } from "./completion-presenter.js";

export function completionCard(item) {
  const status = completionStatus(item.status);
  return `<article class="jcr-missing-card status-${status.tone}">
    <header><div><strong>${escapeHtml(item.driver_name)}</strong>
      <small>${escapeHtml(item.plate || "Mezzo non associato")} · ${escapeHtml(item.vehicle_model || "Modello non registrato")}</small></div>
      <span class="jcr-completion-status status-${status.tone}">${escapeHtml(status.label)}</span></header>
    <dl><div><dt>Planning</dt><dd>${item.planning_id}</dd></div>
      <div><dt>Procedura mancante</dt><dd>${escapeHtml(item.procedure_label)}</dd></div>
      <div><dt>Ora prevista</dt><dd>${escapeHtml(item.expected_time)}</dd></div>
      <div><dt>Ritardo</dt><dd>${escapeHtml(item.delay_label)}</dd></div></dl>
    <div class="jcr-missing-actions">
      <button type="button" class="quiet" data-jcr-missing-driver="${escapeHtml(item.driver_id || item.driver_name)}">Apri Driver</button>
      <button type="button" data-jcr-missing-gdb="${escapeHtml(item.procedure_id || "")}" data-jcr-missing-driver-name="${escapeHtml(item.driver_name)}">Apri GDB</button>
    </div>
  </article>`;
}

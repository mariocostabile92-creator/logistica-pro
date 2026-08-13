import { escapeHtml } from "../../utils/dom.js";
import { facts, infoSection, operationLabel, procedureDateParts } from "./components.js";
import { liveStatusPresentation } from "./live-overview.js";
import { driverDisplayName } from "./driver-display.js";
import { journalMediaSection } from "./media-section.js";

const liveTimeline = item => {
  const events = [
    [item.created_at, "Procedura generata"],
    [item.opened_at, "Procedura aperta"],
    [item.in_progress_at, "Compilazione avviata"],
    [item.occurred_at && !item.incomplete ? item.occurred_at : null, item.anomaly_present ? "Completata con anomalia" : "Procedura completata"],
  ].filter(([at]) => at);
  return `<ol>${events.map(([at, label]) => `<li><time>${escapeHtml(procedureDateParts({ ...item, occurred_at: at }).full)}</time><strong>${escapeHtml(label)}</strong></li>`).join("")}</ol>`;
};

export function journalLiveDetail(item) {
  if (!item) return `<div class="view-state"><strong>Seleziona un driver</strong><p>Apri una procedura per monitorarne l'avanzamento.</p></div>`;
  const status = liveStatusPresentation(item);
  return `<button type="button" class="quiet jcr-back" data-jcr-back>← Torna alla lista</button>
    <header class="jcr-detail-hero"><div><p class="eyebrow">Monitoraggio live</p><h3>${escapeHtml(driverDisplayName(item))}</h3></div>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <div class="jcr-live-detail-layout">
      ${infoSection("Stato corrente", "jcr-live-status", facts([
        ["Veicolo", `${item.plate_snapshot} · ${item.vehicle_model || "Modello non registrato"}`],
        ["Procedura", operationLabel(item.operation_type)], ["Origine", item.origin],
        ["Ultimo aggiornamento", procedureDateParts(item).full],
      ]))}
      ${infoSection("Timeline essenziale", "jcr-timeline", liveTimeline(item))}
      ${infoSection("Anomalie", "jcr-anomalies", item.anomaly_present
        ? facts([["Stato", "Anomalia segnalata"], ["Descrizione", item.anomaly_description || "Descrizione non disponibile"]])
        : `<div class="jcr-empty">Nessuna anomalia segnalata.</div>`)}
      ${journalMediaSection(item.media, false, item)}
      ${infoSection("Azioni", "jcr-actions-section", `<div class="jcr-actions">
        <button type="button" class="primary" data-jcr-open-archive="${escapeHtml(item.id)}" data-jcr-operational-date="${escapeHtml(item.operational_date)}">Apri GDB completo</button>
        ${item.damage_case_id ? `<button type="button" class="secondary" data-jcr-damage="${item.damage_case_id}">Apri pratica danno</button>` : ""}
      </div>`)}
    </div>`;
}

import { escapeHtml } from "../../utils/dom.js";

const value = (count) => count == null ? "Dato non determinabile" : `${count} giorni`;
const dateValue = (date) => date || "Non disponibile";

export function consecutivityCard(driver) {
  const item = driver.consecutivity || {};
  const plannedDifferent = item.planned_consecutive_days != null
    && item.planned_consecutive_days !== item.effective_consecutive_days;
  return `<section class="workforce-consecutivity-card" data-consecutivity-status="${escapeHtml(item.calculated_status || "dati_insufficienti")}">
    <div><span>Consecutivita effettiva</span><strong>${escapeHtml(value(item.effective_consecutive_days))}</strong></div>
    ${plannedDifferent ? `<div><span>Incluso piano finalizzato</span><strong>${escapeHtml(value(item.planned_consecutive_days))}</strong></div>` : ""}
    <div><span>Ultimo lavoro</span><strong>${escapeHtml(dateValue(item.last_worked_date))}</strong></div>
    <div><span>Prossimo piano</span><strong>${escapeHtml(dateValue(item.next_planned_work_date))}</strong></div>
    <p>${escapeHtml(item.reason || "Storico lavorativo non sufficiente per calcolare la consecutivita.")}</p>
    ${item.override ? '<span class="workforce-override-badge">Override attivo</span>' : ""}
  </section>`;
}

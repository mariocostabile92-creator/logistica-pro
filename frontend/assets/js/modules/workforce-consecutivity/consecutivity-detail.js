import { escapeHtml } from "../../utils/dom.js";

const count = (value) => value == null ? "Dato non determinabile" : `${value} giorni`;

export function consecutivityDetail(driver) {
  const item = driver.consecutivity || {};
  const sequence = (item.sequence || []).map((day) => `<li data-day-state="${escapeHtml(day.state)}" title="${escapeHtml(day.reason)}"><time>${escapeHtml(day.date.slice(5))}</time><span>${escapeHtml(day.state)}</span></li>`).join("");
  return `<section class="workforce-consecutivity-detail" aria-labelledby="workforceConsecutivityDetailTitle">
    <h4 id="workforceConsecutivityDetailTitle">Consecutivita</h4>
    <dl class="workforce-availability-detail-grid">
      <div><dt>Effettiva</dt><dd>${escapeHtml(count(item.effective_consecutive_days))}</dd></div>
      <div><dt>Pianificata</dt><dd>${escapeHtml(count(item.planned_consecutive_days))}</dd></div>
      <div><dt>Ultimo lavoro</dt><dd>${escapeHtml(item.last_worked_date || "Non disponibile")}</dd></div>
      <div><dt>Ultimo riposo</dt><dd>${escapeHtml(item.last_rest_date || "Non disponibile")}</dd></div>
      <div><dt>Prossimo lavoro</dt><dd>${escapeHtml(item.next_planned_work_date || "Non disponibile")}</dd></div>
      <div><dt>Policy</dt><dd>Attenzione ${item.threshold_warning} · Limite ${item.threshold_rest_required}</dd></div>
    </dl>
    <p>${escapeHtml(item.reason || "Valutazione non disponibile.")}</p>
    <p class="workforce-policy-note">${escapeHtml(item.policy_message || "Valutazione basata sulla policy operativa dell'organizzazione.")}</p>
    <ul class="workforce-consecutivity-strip" aria-label="Sequenza giornate analizzate">${sequence}</ul>
    <p><strong>Fonti:</strong> ${escapeHtml(item.source_summary?.join(", ") || "Nessuna fonte sufficiente")}</p>
    ${item.override ? `<aside class="workforce-override-summary"><strong>Override applicato</strong><span>${escapeHtml(item.override.reason)}</span><small>${escapeHtml(item.override.created_by)} · ${escapeHtml(item.override.created_at)}</small></aside>` : ""}
    ${driver.permissions?.can_override ? `<button type="button" class="quiet" data-workforce-override-open="${driver.workforce_member_id}">Applica override</button>` : ""}
  </section>`;
}

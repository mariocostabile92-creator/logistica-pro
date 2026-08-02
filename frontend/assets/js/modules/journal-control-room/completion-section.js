import { escapeHtml } from "../../utils/dom.js";
import { completionCard } from "./completion-card.js";
import { completionKpis } from "./completion-kpi.js";
import { completionPlanningLabel } from "./completion-presenter.js";

const emptyCompletion = operationalDate => ({
  planning_id: null, operational_date: operationalDate || "—", drivers_expected: 0,
  check_out: { expected: 0, completed: 0, missing: 0 },
  check_in: { expected: 0, completed: 0, missing: 0 },
  procedures: { open: 0, in_progress: 0, late: 0, anomalies: 0 },
  missing: [], exceptions: [], active_filter: "all",
});

export function journalCompletionSection(payload, activeFilter = "all", operationalDate = null) {
  const completion = payload || emptyCompletion(operationalDate);
  return `<section class="jcr-completion" aria-labelledby="journalCompletionTitle">
    <header><div><p class="eyebrow">Controllo completamento</p><h3 id="journalCompletionTitle">Journal Completion</h3>
      <p>${escapeHtml(completionPlanningLabel(completion))}</p></div>
      ${activeFilter !== "all" ? '<button type="button" class="quiet" data-jcr-completion-reset>Rimuovi filtro</button>' : ""}</header>
    <div class="jcr-completion-kpis">${completionKpis(completion, activeFilter)}</div>
    <section class="jcr-missing" aria-labelledby="journalMissingTitle"><header>
      <div><h4 id="journalMissingTitle">Driver con GDB mancanti</h4><p>${completion.missing.length} procedure richiedono attenzione.</p></div>
      ${completion.exceptions.length ? `<span>${completion.exceptions.length} eccezioni escluse</span>` : ""}</header>
      <div class="jcr-missing-list">${completion.missing.length
        ? completion.missing.map(completionCard).join("")
        : '<div class="view-state"><strong>Nessun GDB mancante</strong><p>Non risultano scostamenti per il filtro selezionato.</p></div>'}</div>
    </section>
  </section>`;
}

import {
  currentSuggestion,
  suggestionReviewProgress,
} from "./suggestion-review.js?v=1";


const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


function chooserMarkup(state) {
  if (!state.chooserOpen) return "";
  const selectedId = state.currentSelection?.workforce_member_id;
  const results = state.candidatePhase === "loading"
    ? '<p class="dsp-quality-review-neutral" role="status">Ricerca Workforce…</p>'
    : state.candidatePhase === "available" && !state.candidates.length
      ? '<p class="dsp-quality-review-neutral" role="status">Nessun driver Workforce trovato.</p>'
      : `<div class="dsp-quality-review-candidates" role="listbox" aria-label="Risultati Workforce">${state.candidates.map(candidate => `
          <button type="button" role="option" aria-selected="${selectedId === candidate.workforce_member_id}"
            data-quality-review-candidate="${escapeHtml(candidate.workforce_member_id)}">
            <strong>${escapeHtml(candidate.display_name)}</strong>
            <span>${escapeHtml(candidate.station || "Station non indicata")} · ${escapeHtml(candidate.contract || "Contratto non indicato")}</span>
          </button>
        `).join("")}</div>`;
  return `
    <section class="dsp-quality-review-chooser" aria-labelledby="qualityReviewChooserTitle">
      <header><h4 id="qualityReviewChooserTitle">Scegli un altro driver</h4><button type="button" class="secondary" data-quality-review-choose-close>Chiudi selettore</button></header>
      <label for="qualityReviewWorkforceSearch">Cerca in Workforce</label>
      <input id="qualityReviewWorkforceSearch" type="search" data-quality-review-search
        value="${escapeHtml(state.candidateSearch)}" placeholder="Nome, ID o station" autocomplete="off" />
      ${results}
      ${state.currentSelection ? `
        <div class="dsp-quality-review-selection" role="status"><span>Driver selezionato</span><strong>${escapeHtml(state.currentSelection.display_name)}</strong></div>
        <button type="button" class="primary" data-quality-review-confirm-selected ${state.saving ? "disabled" : ""}>Conferma questo driver</button>
      ` : '<p class="dsp-quality-review-neutral">Seleziona un risultato. Il click non salva l’associazione.</p>'}
    </section>
  `;
}


function completionMarkup(state, preview) {
  const progress = suggestionReviewProgress(state);
  const unresolved = Number(preview?.coverage?.unresolved || 0);
  return `
    <div class="dsp-quality-review-complete">
      <p class="eyebrow">Revisione completata</p>
      <h3 id="qualitySuggestionReviewTitle">Revisione completata</h3>
      <dl aria-label="Esito revisione">
        <div><dt>Confermati</dt><dd>${progress.confirmed}</dd></div>
        <div><dt>Saltati</dt><dd>${progress.skipped}</dd></div>
        <div><dt>Ancora non risolti</dt><dd>${unresolved}</dd></div>
      </dl>
      <div class="dsp-quality-review-actions">
        <button type="button" class="primary" data-quality-review-close>Torna alle associazioni</button>
        ${unresolved ? '<button type="button" class="secondary" data-quality-review-unresolved>Gestisci i non trovati</button>' : ""}
      </div>
    </div>
  `;
}


export function suggestionReviewMarkup(state = {}, preview = {}) {
  if (!state.open) return "";
  const progress = suggestionReviewProgress(state);
  if (progress.complete) {
    return `<section class="dsp-quality-suggestion-review" role="dialog" aria-modal="true" aria-labelledby="qualitySuggestionReviewTitle">${completionMarkup(state, preview)}</section>`;
  }
  const row = currentSuggestion(state);
  if (!row) return "";
  return `
    <section class="dsp-quality-suggestion-review" role="dialog" aria-modal="true" aria-labelledby="qualitySuggestionReviewTitle">
      <header>
        <div><p class="eyebrow">Revisione associazioni</p><h3 id="qualitySuggestionReviewTitle">Revisione associazioni</h3></div>
        <button type="button" class="secondary" data-quality-review-close aria-label="Chiudi revisione">Chiudi</button>
      </header>
      <div class="dsp-quality-review-progress" role="status" aria-live="polite">
        <strong>${state.currentIndex + 1} di ${progress.total}</strong>
        <span>${progress.confirmed} verificati · ${progress.remaining} rimanenti · ${progress.skipped} saltati</span>
      </div>
      ${state.feedback ? `<p class="dsp-quality-review-feedback" role="status">${escapeHtml(state.feedback)}</p>` : ""}
      <article class="dsp-quality-review-card">
        <div><span>Transporter ID</span><strong>${escapeHtml(row.transporter_external_id)}</strong></div>
        <div><span>Fonte driver</span><strong>${escapeHtml(row.source_driver_value || "Non disponibile")}</strong></div>
        <div><span>Workforce suggerito</span><strong>${escapeHtml(row.proposed_display_name || "Non disponibile")}</strong></div>
        <div><span>Fonte evidenza</span><strong>${escapeHtml(row.evidence_source || "NAME_SUGGESTION")}</strong></div>
        <div><span>Confidence</span><strong>${escapeHtml(row.confidence || row.status || "SUGGESTED")}</strong></div>
        <div><span>Stato</span><strong>Da verificare</strong><small>${escapeHtml(row.reason || "Richiede conferma umana.")}</small></div>
      </article>
      <div class="dsp-quality-review-actions">
        <button type="button" class="primary" data-quality-review-confirm ${!row.proposed_workforce_member_id || state.saving ? "disabled" : ""}>Conferma</button>
        <button type="button" class="secondary" data-quality-review-choose ${state.saving ? "disabled" : ""}>Scegli altro</button>
        <button type="button" class="secondary" data-quality-review-skip ${state.saving ? "disabled" : ""}>Salta</button>
      </div>
      <p class="dsp-quality-review-shortcuts" aria-label="Scorciatoie tastiera"><kbd>Invio</kbd> Conferma <kbd>E</kbd> Scegli altro <kbd>S</kbd> Salta <kbd>Esc</kbd> Chiudi</p>
      ${chooserMarkup(state)}
      ${state.error ? `<p class="dsp-quality-reconciliation-error" role="alert">${escapeHtml(state.error)}</p>` : ""}
    </section>
  `;
}


export function mountSuggestionReview(root, state = {}, preview = {}) {
  const host = root?.querySelector?.("[data-quality-suggestion-review-host]");
  if (!host) return false;
  const markup = suggestionReviewMarkup(state, preview);
  host.innerHTML = markup;
  host.hidden = !markup;
  return Boolean(markup);
}

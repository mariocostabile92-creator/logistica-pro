import { identityRowsForBucket } from "./identity-source.js?v=3";


const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


function sourcePicker() {
  return `
    <div class="dsp-quality-source-picker" data-quality-identity-dropzone>
      <input class="visually-hidden" id="qualityIdentitySourceFile" type="file"
        accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
        data-quality-identity-file />
      <button type="button" class="primary" data-quality-identity-pick>Carica file</button>
      <button type="button" class="secondary" data-quality-identity-planning>Usa ultimo Planning</button>
    </div>
  `;
}


function schemaSelection(state) {
  const source = state.preview?.source || {};
  const options = values => values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  return `
    <div class="dsp-quality-source-schema" role="status">
      <strong>La struttura richiede una conferma.</strong>
      ${source.candidate_sheets?.length ? `<label>Foglio<select data-quality-identity-selection="sheet"><option value="">Seleziona</option>${options(source.candidate_sheets)}</select></label>` : ""}
      ${source.transporter_candidates?.length ? `<label>Colonna Transporter<select data-quality-identity-selection="transporterColumn"><option value="">Seleziona</option>${options(source.transporter_candidates)}</select></label>` : ""}
      ${source.driver_candidates?.length ? `<label>Colonna driver<select data-quality-identity-selection="driverColumn"><option value="">Seleziona</option>${options(source.driver_candidates)}</select></label>` : ""}
      <button type="button" class="primary" data-quality-identity-analyze>Analizza selezione</button>
    </div>
  `;
}


function coverageMarkup(coverage = {}, associatedCount = 0) {
  const cards = [
    ["Transporter scorecard", coverage.quality_transporters],
    ["Già associati", Number(coverage.already_verified || 0) + associatedCount],
    ["Corrispondenze certe", coverage.exact_matches],
    ["Da verificare", Math.max(0, Number(coverage.suggestions || 0) - associatedCount)],
    ["Non trovati", coverage.unresolved],
    ["Conflitti", coverage.conflicts],
  ];
  return `<dl class="dsp-quality-source-coverage">${cards.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? 0)}</dd></div>`).join("")}</dl>`;
}


function reconciliationRow(state, externalId) {
  return (state.reconciliationRows || []).find(
    item => item.transporter_external_id === externalId,
  ) || null;
}


export function isSafeInlineSuggestion(row, mapping = null) {
  return Boolean(
    row?.status === "SUGGESTED"
    && Number.isInteger(Number(row.proposed_workforce_member_id))
    && Number(row.proposed_workforce_member_id) > 0
    && mapping?.mapping_status === "UNMAPPED"
    && !mapping?.workforce_member_id
  );
}


function suggestionAssociated(state, row, mapping) {
  return mapping?.mapping_status === "MATCHED"
    || state.confirmedSuggestionIds?.includes(row.transporter_external_id);
}


function rowMarkup(row, state) {
  const mapping = reconciliationRow(state, row.transporter_external_id);
  const associated = row.status === "SUGGESTED" && suggestionAssociated(state, row, mapping);
  const safe = isSafeInlineSuggestion(row, mapping) && !associated;
  const saving = state.savingSuggestionIds?.includes(row.transporter_external_id);
  const failed = state.failedSuggestionIds?.includes(row.transporter_external_id);
  const selected = state.selectedSuggestionIds?.includes(row.transporter_external_id);
  const status = associated ? "ASSOCIATO" : row.status;
  const workforceName = associated
    ? (mapping?.workforce_display_name || row.proposed_display_name || "Associato")
    : (row.proposed_display_name || "Non trovato");
  const suggestionControls = row.status === "SUGGESTED" ? `
      <label class="dsp-quality-source-select">
        <input type="checkbox" data-quality-suggestion-select="${escapeHtml(row.transporter_external_id)}"
          ${selected ? "checked" : ""} ${safe && !saving && !state.bulkSaving ? "" : "disabled"} />
        <span>Seleziona suggerimento</span>
      </label>
      <div class="dsp-quality-source-row-actions">
        ${safe ? `
          <button type="button" class="primary" data-quality-suggestion-confirm="${escapeHtml(row.transporter_external_id)}" ${saving || state.bulkSaving ? "disabled" : ""}>${saving ? "Salvataggio…" : "Conferma"}</button>
          <button type="button" class="secondary" data-quality-suggestion-choose="${escapeHtml(row.transporter_external_id)}" ${saving || state.bulkSaving ? "disabled" : ""}>Scegli altro</button>
        ` : associated ? '<strong class="dsp-quality-source-associated">Associazione confermata</strong>' : '<small>Associazione non confermabile da questo suggerimento.</small>'}
      </div>
      ${failed ? '<p class="dsp-quality-reconciliation-error" role="alert">Associazione non salvata. Riprova.</p>' : ""}
    ` : "";
  return `
    <article class="dsp-quality-source-row" data-source-status="${escapeHtml(status)}" data-quality-suggestion-row="${escapeHtml(row.transporter_external_id)}">
      <div><span>T-ID</span><strong>${escapeHtml(row.transporter_external_id)}</strong></div>
      <div><span>Fonte</span><strong>${escapeHtml(row.source_driver_value || "Non disponibile")}</strong></div>
      <div><span>${associated ? "Workforce" : "Possibile Workforce"}</span><strong>${escapeHtml(workforceName)}</strong></div>
      <div><span>Stato</span><strong>${escapeHtml(status)}</strong><small>${escapeHtml(row.reason)}</small></div>
      ${suggestionControls}
    </article>
  `;
}


function bulkDialogMarkup(state, selectedCount) {
  if (!state.bulkDialogOpen) return "";
  return `
    <section class="dsp-quality-bulk-dialog" role="dialog" aria-modal="true" aria-labelledby="qualityBulkConfirmTitle">
      <h4 id="qualityBulkConfirmTitle">Conferma associazioni selezionate</h4>
      <p>Stai per associare ${escapeHtml(selectedCount)} Transporter ai driver Workforce suggeriti.</p>
      <p>Le associazioni potranno essere modificate successivamente.</p>
      <div>
        <button type="button" class="secondary" data-quality-suggestion-bulk-cancel>Annulla</button>
        <button type="button" class="primary" data-quality-suggestion-bulk-final ${selectedCount && !state.bulkSaving ? "" : "disabled"}>Conferma ${escapeHtml(selectedCount)} associazioni</button>
      </div>
    </section>
  `;
}


function previewMarkup(state) {
  const preview = state.preview;
  const source = preview.source || {};
  const rows = identityRowsForBucket(preview.rows || [], state.bucket);
  const suggestionRows = identityRowsForBucket(preview.rows || [], "suggested");
  const associatedCount = suggestionRows.filter(row => suggestionAssociated(
    state,
    row,
    reconciliationRow(state, row.transporter_external_id),
  )).length;
  const safeRows = suggestionRows.filter(row => {
    const mapping = reconciliationRow(state, row.transporter_external_id);
    return isSafeInlineSuggestion(row, mapping) && !suggestionAssociated(state, row, mapping);
  });
  const selectedIds = (state.selectedSuggestionIds || []).filter(id => (
    safeRows.some(row => row.transporter_external_id === id)
  ));
  const allSelected = safeRows.length > 0 && safeRows.every(
    row => selectedIds.includes(row.transporter_external_id),
  );
  const suggestions = Math.max(0, Number(preview.coverage?.suggestions || 0) - associatedCount);
  const buckets = [
    ["exact", "Certe", preview.coverage?.exact_matches || 0],
    ["suggested", "Da verificare", suggestions],
    ["unresolved", "Non trovate", preview.coverage?.unresolved || 0],
    ["conflict", "Conflitti", preview.coverage?.conflicts || 0],
  ];
  const rowsList = `<div class="dsp-quality-source-rows">${rows.length
    ? rows.map(row => rowMarkup(row, state)).join("")
    : '<p class="dsp-quality-reconciliation-neutral">Nessuna evidenza in questa categoria.</p>'}</div>`;
  const rowsMarkup = state.bucket === "suggested"
    ? `<div class="dsp-quality-source-inline-toolbar">
        <label><input type="checkbox" data-quality-suggestion-select-all ${allSelected ? "checked" : ""} ${safeRows.length && !state.bulkSaving ? "" : "disabled"} /> Seleziona tutti i suggerimenti visibili</label>
        <button type="button" class="primary" data-quality-suggestion-bulk-open ${selectedIds.length && !state.bulkSaving ? "" : "disabled"}>Conferma selezionati (${escapeHtml(selectedIds.length)})</button>
      </div>
      ${state.bulkResult ? `<p class="dsp-quality-source-bulk-result" role="status">${escapeHtml(state.bulkResult.confirmed)} associazioni confermate. ${escapeHtml(state.bulkResult.failed)} da rivedere.</p>` : ""}
      ${rowsList}${bulkDialogMarkup(state, selectedIds.length)}`
    : rowsList;
  return `
    <div class="dsp-quality-source-detection">
      <div><span>File</span><strong>${escapeHtml(source.filename)}</strong></div>
      <div><span>Foglio</span><strong>${escapeHtml(source.sheet || "—")}</strong></div>
      <div><span>Transporter column</span><strong>${escapeHtml(source.transporter_column || "—")}</strong></div>
      <div><span>Driver column</span><strong>${escapeHtml(source.driver_column || "—")}</strong></div>
      <div><span>Rows detected</span><strong>${escapeHtml(source.rows_detected || 0)}</strong></div>
    </div>
    ${coverageMarkup(preview.coverage, associatedCount)}
    <div class="dsp-quality-source-buckets" role="group" aria-label="Filtra evidenze">${buckets.map(([key, label, count]) => `
      <button type="button" data-quality-identity-bucket="${key}" aria-pressed="${state.bucket === key}" class="${state.bucket === key ? "active" : ""}">${label} (${count})</button>
    `).join("")}</div>
    ${preview.coverage?.exact_matches ? `<button type="button" class="primary dsp-quality-source-apply" data-quality-identity-apply>Applica ${escapeHtml(preview.coverage.exact_matches)} associazioni certe</button>` : ""}
    ${rowsMarkup}
  `;
}


export function identitySourceMarkup(state = {}) {
  const busy = ["loading", "applying"].includes(state.phase);
  return `
    <section class="dsp-quality-identity-source" aria-labelledby="qualityIdentitySourceTitle" ${busy ? 'aria-busy="true"' : ""}>
      <header>
        <div>
          <p class="eyebrow">Metodo consigliato</p>
          <h3 id="qualityIdentitySourceTitle">Riconcilia da una fonte</h3>
          <p>Se disponi di un file con Transporter ID (T-ID) e driver, caricalo per individuare automaticamente le corrispondenze disponibili.</p>
          <small>Le associazioni non certe resteranno da verificare manualmente.</small>
        </div>
        ${state.phase !== "idle" ? '<button type="button" class="secondary" data-quality-identity-reset>Nuova fonte</button>' : ""}
      </header>
      ${state.phase === "idle" ? sourcePicker() : ""}
      ${state.phase === "loading" ? '<p role="status">Analisi della fonte in corso…</p>' : ""}
      ${state.phase === "schema" ? schemaSelection(state) : ""}
      ${["available", "applying", "applied"].includes(state.phase) && state.preview?.valid ? previewMarkup(state) : ""}
      <div data-quality-suggestion-review-host hidden></div>
      ${state.phase === "applied" ? `<p class="dsp-quality-source-success" role="status">${escapeHtml(state.result?.applied || 0)} associazioni applicate. ${escapeHtml(state.result?.already_verified || 0)} già verificate.</p>` : ""}
      ${state.error ? `<p class="dsp-quality-reconciliation-error" role="alert">${escapeHtml(state.error)}</p>` : ""}
      <p class="dsp-quality-source-manual">Non hai un file? <strong>Associa manualmente</strong> dalla lista sotto.</p>
    </section>
  `;
}

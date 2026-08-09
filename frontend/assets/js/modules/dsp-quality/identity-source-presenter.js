import { identityRowsForBucket } from "./identity-source.js?v=1";
import { suggestionReviewMarkup } from "./suggestion-review-presenter.js?v=1";


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


function coverageMarkup(coverage = {}) {
  const cards = [
    ["Transporter scorecard", coverage.quality_transporters],
    ["Già associati", coverage.already_verified],
    ["Corrispondenze certe", coverage.exact_matches],
    ["Da verificare", coverage.suggestions],
    ["Non trovati", coverage.unresolved],
    ["Conflitti", coverage.conflicts],
  ];
  return `<dl class="dsp-quality-source-coverage">${cards.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? 0)}</dd></div>`).join("")}</dl>`;
}


function rowMarkup(row) {
  return `
    <article class="dsp-quality-source-row" data-source-status="${escapeHtml(row.status)}">
      <div><span>T-ID</span><strong>${escapeHtml(row.transporter_external_id)}</strong></div>
      <div><span>Fonte</span><strong>${escapeHtml(row.source_driver_value || "Non disponibile")}</strong></div>
      <div><span>Possibile Workforce</span><strong>${escapeHtml(row.proposed_display_name || "Non trovato")}</strong></div>
      <div><span>Stato</span><strong>${escapeHtml(row.status)}</strong><small>${escapeHtml(row.reason)}</small></div>
    </article>
  `;
}


function previewMarkup(state) {
  const preview = state.preview;
  const source = preview.source || {};
  const rows = identityRowsForBucket(preview.rows || [], state.bucket);
  const buckets = [
    ["exact", "Certe", preview.coverage?.exact_matches || 0],
    ["suggested", "Da verificare", preview.coverage?.suggestions || 0],
    ["unresolved", "Non trovate", preview.coverage?.unresolved || 0],
    ["conflict", "Conflitti", preview.coverage?.conflicts || 0],
  ];
  const suggestions = Number(preview.coverage?.suggestions || 0);
  const rowsList = `<div class="dsp-quality-source-rows">${rows.length
    ? rows.map(rowMarkup).join("")
    : '<p class="dsp-quality-reconciliation-neutral">Nessuna evidenza in questa categoria.</p>'}</div>`;
  const rowsMarkup = state.bucket === "suggested"
    ? `<div class="dsp-quality-source-review-entry">
        <div><strong>${escapeHtml(suggestions)} da verificare</strong><span>Rivedi una corrispondenza alla volta con conferma umana.</span></div>
        <button type="button" class="primary" data-quality-suggestion-review-open ${suggestions ? "" : "disabled"}>Rivedi suggerimenti</button>
      </div>${rowsList}`
    : rowsList;
  return `
    <div class="dsp-quality-source-detection">
      <div><span>File</span><strong>${escapeHtml(source.filename)}</strong></div>
      <div><span>Foglio</span><strong>${escapeHtml(source.sheet || "—")}</strong></div>
      <div><span>Transporter column</span><strong>${escapeHtml(source.transporter_column || "—")}</strong></div>
      <div><span>Driver column</span><strong>${escapeHtml(source.driver_column || "—")}</strong></div>
      <div><span>Rows detected</span><strong>${escapeHtml(source.rows_detected || 0)}</strong></div>
    </div>
    ${coverageMarkup(preview.coverage)}
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
      ${suggestionReviewMarkup(state.review, state.preview)}
      ${state.phase === "applied" ? `<p class="dsp-quality-source-success" role="status">${escapeHtml(state.result?.applied || 0)} associazioni applicate. ${escapeHtml(state.result?.already_verified || 0)} già verificate.</p>` : ""}
      ${state.error ? `<p class="dsp-quality-reconciliation-error" role="alert">${escapeHtml(state.error)}</p>` : ""}
      <p class="dsp-quality-source-manual">Non hai un file? <strong>Associa manualmente</strong> dalla lista sotto.</p>
    </section>
  `;
}

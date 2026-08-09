import {
  formatQualityFileSize,
  qualityActionLabel,
} from "./import.js";


const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


function value(value, fallback = "Non disponibile") {
  return value == null || value === "" ? fallback : escapeHtml(value);
}


function fileInput() {
  return '<input class="visually-hidden" data-quality-file type="file" accept="application/pdf,.pdf" aria-label="Seleziona scorecard Amazon PDF" />';
}


function shell(content) {
  return `
    <header class="dsp-quality-heading">
      <p class="eyebrow">Qualità settimanale</p>
      <h2>Scorecard Amazon</h2>
      <p>Importa la scorecard settimanale per analizzare performance, metriche e qualità operativa.</p>
    </header>
    ${content}
  `;
}


export function qualityEmptyMarkup(canImport) {
  const action = canImport ? `
    ${fileInput()}
    <div class="dsp-quality-dropzone" data-quality-dropzone>
      <strong>Trascina qui la scorecard PDF</strong>
      <span>oppure selezionala dal dispositivo</span>
      <button type="button" data-quality-pick>Importa scorecard</button>
    </div>
  ` : `
    <div class="dsp-quality-permission" role="status">
      <strong>Consultazione Quality</strong>
      <span>Non disponi del permesso per importare scorecard.</span>
    </div>
  `;
  return shell(`<section class="dsp-quality-empty">${action}</section>`);
}


function fileSummary(file, loadingLabel = "") {
  return `
    <div class="dsp-quality-file-summary">
      <div><strong>${escapeHtml(file?.name || "Scorecard PDF")}</strong><span>${formatQualityFileSize(file?.size || 0)}</span></div>
      ${loadingLabel ? `<p class="dsp-quality-loading" role="status"><span aria-hidden="true"></span>${escapeHtml(loadingLabel)}</p>` : ""}
    </div>
  `;
}


function identityMarkup(preview) {
  const identity = preview.identity || {};
  return `
    <dl class="dsp-quality-identity" aria-label="Identità scorecard">
      <div><dt>DSP</dt><dd>${value(identity.dsp_identifier)}</dd></div>
      <div><dt>Station</dt><dd>${value(identity.station)}</dd></div>
      <div><dt>Periodo</dt><dd>Week ${value(identity.reported_week, "—")} / ${value(identity.reported_year, "—")}</dd></div>
      <div><dt>Overall</dt><dd>${value(identity.overall_score, "—")}</dd></div>
      <div><dt>Standing</dt><dd>${value(identity.overall_standing, "—")}</dd></div>
      <div><dt>Rank</dt><dd>${value(identity.rank, "—")}</dd></div>
    </dl>
  `;
}


function countsMarkup(counts = {}) {
  const items = [
    ["Metriche DSP", counts.dsp_metrics_count],
    ["Transporter", counts.transporter_rows_count],
    ["Focus area", counts.focus_areas_count],
    ["Standard", counts.standards_count],
    ["Eccezioni WH", counts.working_hours_exception_count],
  ];
  return `<dl class="dsp-quality-counts" aria-label="Contenuto rilevato">${items.map(([label, count]) => `
    <div><dt>${label}</dt><dd>${value(count, "0")}</dd></div>
  `).join("")}</dl>`;
}


function validationMarkup(validation = {}) {
  const groups = [
    ["error", "ERROR", validation.errors || []],
    ["warning", "WARNING", validation.warnings || []],
    ["info", "INFO", validation.infos || []],
  ].filter(([, , messages]) => messages.length);
  if (!groups.length) return '<div class="dsp-quality-validation is-valid" role="status"><strong>Validazione completata</strong><span>Nessun problema rilevato.</span></div>';
  return `<div class="dsp-quality-validation" aria-label="Esito validazione">${groups.map(([tone, label, messages]) => `
    <section class="dsp-quality-validation-group tone-${tone}">
      <h4>${label} <span>${messages.length}</span></h4>
      <ul>${messages.map(message => `<li>${escapeHtml(message.message || "Elemento da verificare")}</li>`).join("")}</ul>
    </section>
  `).join("")}</div>`;
}


function mappingMarkup(mapping = {}) {
  return `
    <section class="dsp-quality-mapping">
      <h3>Riepilogo mapping driver</h3>
      <dl>
        <div><dt>Associati</dt><dd>${value(mapping.matched_transporters, "0")}</dd></div>
        <div><dt>Non associati</dt><dd>${value(mapping.unmapped_transporters, "0")}</dd></div>
        <div><dt>Ambigui</dt><dd>${value(mapping.ambiguous_transporters, "0")}</dd></div>
      </dl>
    </section>
  `;
}


export function qualityPreviewMarkup(view) {
  const preview = view.preview;
  const action = preview.idempotency?.action;
  return shell(`
    ${fileInput()}
    ${fileSummary(view.file)}
    ${view.error ? `<p class="dsp-quality-error" role="alert">${escapeHtml(view.error)}</p>` : ""}
    <section class="dsp-quality-preview" aria-label="Preview scorecard">
      ${identityMarkup(preview)}
      ${countsMarkup(preview.counts)}
      ${validationMarkup(preview.validation)}
      ${mappingMarkup(preview.mapping)}
      <p class="dsp-quality-idempotency" data-action="${escapeHtml(action || "UNKNOWN")}">${escapeHtml(qualityActionLabel(action))}</p>
      <div class="dsp-quality-actions">
        <button type="button" class="secondary" data-quality-pick>Scegli un altro PDF</button>
        <button type="button" data-quality-confirm ${view.canConfirm ? "" : "disabled"}>Conferma importazione</button>
      </div>
    </section>
  `);
}


function overviewMarkup(view) {
  if (!view.overviewVisible) return "";
  const section = view.section;
  return `
    <section class="dsp-quality-scorecard-shell" aria-label="Scorecard importata">
      <nav class="dsp-quality-section-tabs" role="tablist" aria-label="Sezioni scorecard">
        ${[["overview", "Panoramica"], ["metrics", "Metriche"], ["drivers", "Driver"]].map(([key, label]) => `
          <button type="button" role="tab" data-quality-section="${key}" aria-selected="${section === key}" class="${section === key ? "active" : ""}">${label}</button>
        `).join("")}
      </nav>
      <div class="dsp-quality-section-panel" role="tabpanel">
        ${section === "overview" ? `${identityMarkup(view.preview)}${countsMarkup(view.preview?.counts)}` : `
          <div class="dsp-quality-placeholder"><strong>${section === "metrics" ? "Metriche" : "Driver"}</strong><span>Sezione predisposta per il prossimo sviluppo.</span></div>
        `}
      </div>
    </section>
  `;
}


export function qualitySuccessMarkup(view) {
  const identity = view.preview?.identity || {};
  return shell(`
    <section class="dsp-quality-success" role="status">
      <p class="eyebrow">Import completato</p>
      <h3>Scorecard importata</h3>
      <dl>
        <div><dt>DSP</dt><dd>${value(identity.dsp_identifier)}</dd></div>
        <div><dt>Station</dt><dd>${value(identity.station)}</dd></div>
        <div><dt>Settimana</dt><dd>Week ${value(identity.reported_week, "—")} / ${value(identity.reported_year, "—")}</dd></div>
        <div><dt>Overall</dt><dd>${value(identity.overall_score, "—")}</dd></div>
        <div><dt>Standing</dt><dd>${value(identity.overall_standing, "—")}</dd></div>
        <div><dt>Transporter</dt><dd>${value(view.result?.transporter_rows, "0")}</dd></div>
      </dl>
      <div class="dsp-quality-actions">
        <button type="button" class="secondary" data-quality-reset>Importa un'altra scorecard</button>
        <button type="button" data-quality-overview>Visualizza scorecard</button>
      </div>
    </section>
    ${overviewMarkup(view)}
  `);
}


export function renderDspQuality(root, view) {
  if (!root) return;
  if (view.phase === "empty") root.innerHTML = qualityEmptyMarkup(view.canImport);
  else if (view.phase === "preview-loading") root.innerHTML = shell(fileSummary(view.file, "Analisi scorecard in corso…"));
  else if (view.phase === "import-loading") root.innerHTML = shell(`${fileSummary(view.file, "Importazione scorecard in corso…")}${identityMarkup(view.preview)}`);
  else if (view.phase === "preview-ready") root.innerHTML = qualityPreviewMarkup(view);
  else if (view.phase === "success") root.innerHTML = qualitySuccessMarkup(view);
  else root.innerHTML = shell(`
    ${view.canImport ? fileInput() : ""}
    <div class="dsp-quality-error-state" role="alert"><strong>Scorecard non disponibile</strong><span>${escapeHtml(view.error || "Operazione non riuscita.")}</span></div>
    ${view.canImport ? '<button type="button" data-quality-pick>Seleziona un altro PDF</button>' : ""}
  `);
}

import {
  formatQualityFileSize,
  qualityActionLabel,
} from "./import.js";
import { qualityMetricsMarkup } from "./metrics-presenter.js?v=3";
import { qualityDriversMarkup } from "./drivers-presenter.js?v=7";
import { qualityAttentionMarkup } from "./attention-presenter.js?v=2";
import { mountSuggestionReview } from "./suggestion-review-presenter.js?v=2";


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


export function qualityEmptyMarkup(canImport, { hasExisting = false } = {}) {
  const action = canImport ? `
    ${fileInput()}
    <div class="dsp-quality-dropzone" data-quality-dropzone>
      <strong>Trascina qui la scorecard PDF</strong>
      <span>oppure selezionala dal dispositivo</span>
      <button type="button" data-quality-pick>Importa scorecard</button>
      ${hasExisting ? '<button type="button" class="secondary" data-quality-back>Torna alla panoramica</button>' : ""}
    </div>
  ` : `
    <div class="dsp-quality-permission" role="status">
      <strong>Consultazione Quality</strong>
      <span>Non disponi del permesso per importare scorecard.</span>
    </div>
  `;
  return shell(`<section class="dsp-quality-empty">${action}</section>`);
}


export function qualityLoadingMarkup() {
  return shell(`
    <div class="dsp-quality-latest-loading" role="status" aria-busy="true">
      <span aria-hidden="true"></span>
      <div><strong>Caricamento Quality</strong><p>Recupero dell'ultima scorecard importata.</p></div>
    </div>
  `);
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


function rankWow(valueToFormat) {
  if (valueToFormat == null || valueToFormat === "") return "—";
  const numeric = Number(valueToFormat);
  if (!Number.isFinite(numeric)) return value(valueToFormat, "—");
  return numeric > 0 ? `+${numeric}` : String(numeric);
}


function importedAt(raw) {
  if (!raw) return "Non disponibile";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return value(raw);
  return new Intl.DateTimeFormat("it-IT", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}


function persistedSectionTabs(section) {
  return `
    <nav class="dsp-quality-section-tabs" role="tablist" aria-label="Sezioni scorecard">
      ${[["overview", "Panoramica"], ["attention", "Attenzione"], ["metrics", "Metriche"], ["drivers", "Driver"]].map(([key, label]) => `
        <button type="button" role="tab" data-quality-section="${key}" aria-selected="${section === key}" class="${section === key ? "active" : ""}">${label}</button>
      `).join("")}
    </nav>
  `;
}


function scorecardHistorySelector(view) {
  const items = view.history?.items || [];
  if (!items.length) return "";
  const timelines = new Set(items.map(item => `${item.dsp_identifier}|${item.station}`));
  const showContext = timelines.size > 1;
  const selected = items.find(item => item.scorecard_id === view.selectedScorecardId) || items[0];
  const options = items.map(item => {
    const period = `Week ${item.reported_week} · ${item.reported_year}`;
    const label = showContext
      ? `${item.dsp_identifier} · ${item.station} · ${period}`
      : period;
    return `<option value="${escapeHtml(item.scorecard_id)}" ${item.scorecard_id === view.selectedScorecardId ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  return `
    <section class="dsp-quality-history-selector" aria-labelledby="qualityHistoryLabel">
      <label id="qualityHistoryLabel" for="qualityScorecardSelect">Settimana</label>
      <select id="qualityScorecardSelect" data-quality-scorecard-select aria-describedby="qualityHistoryContext">
        ${options}
      </select>
      <p id="qualityHistoryContext">
        <strong>${value(selected?.dsp_identifier)}</strong>
        <span>${value(selected?.station)} · ${items.length} scorecard disponibili</span>
      </p>
    </section>
  `;
}


function persistedOverview(latest) {
  const scorecard = latest.scorecard || {};
  const revision = latest.revision || {};
  const counts = latest.counts || {};
  const sections = latest.sections || [];
  const focusAreas = latest.focus_areas || [];
  const standingTone = String(revision.overall_standing || "unknown")
    .toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  return `
    <article class="dsp-quality-overview" aria-label="Panoramica Quality persistita">
      <section class="dsp-quality-overall" data-standing="${escapeHtml(standingTone)}">
        <div class="dsp-quality-overall-standing">
          <span>Overall Standing</span>
          <strong>${value(revision.overall_standing, "Non disponibile")}</strong>
        </div>
        <div><span>Overall Score</span><strong>${value(revision.overall_score, "—")}</strong></div>
        <div><span>Rank</span><strong>${value(revision.rank, "—")}</strong></div>
        <div><span>Rank WoW</span><strong>${rankWow(revision.rank_wow_declared)}</strong></div>
        <p><strong>${value(scorecard.dsp_identifier)}</strong> / ${value(scorecard.station)} · Week ${value(scorecard.reported_week, "—")} / ${value(scorecard.reported_year, "—")}</p>
      </section>

      <section class="dsp-quality-focus" aria-labelledby="dspQualityFocusTitle">
        <div class="dsp-quality-block-heading"><p class="eyebrow">Priorità rilevate</p><h3 id="dspQualityFocusTitle">Focus Areas</h3></div>
        ${focusAreas.length ? `<ol>${focusAreas.map(item => `
          <li><span>${value(item.position, "—")}</span><strong>${value(item.source_label)}</strong></li>
        `).join("")}</ol>` : '<p class="dsp-quality-neutral">Nessuna focus area disponibile.</p>'}
      </section>

      <section class="dsp-quality-standings" aria-labelledby="dspQualityStandingsTitle">
        <div class="dsp-quality-block-heading"><p class="eyebrow">Sezioni Amazon</p><h3 id="dspQualityStandingsTitle">Section standings</h3></div>
        ${sections.length ? `<ul>${sections.map(item => `
          <li><span>${value(item.label)}</span><strong>${value(item.standing)}</strong></li>
        `).join("")}</ul>` : '<p class="dsp-quality-neutral">Standing di sezione non disponibili.</p>'}
      </section>

      <div class="dsp-quality-secondary-grid">
        <section class="dsp-quality-persisted-counts" aria-labelledby="dspQualityCountsTitle">
          <h3 id="dspQualityCountsTitle">Contenuto importato</h3>
          <dl>
            <div><dt>Transporter</dt><dd>${value(counts.transporter_rows, "0")}</dd></div>
            <div><dt>Metriche DSP</dt><dd>${value(counts.dsp_metrics, "0")}</dd></div>
            <div><dt>Eccezioni WH</dt><dd>${value(counts.working_hour_exceptions, "0")}</dd></div>
          </dl>
        </section>
        <section class="dsp-quality-persisted-mapping" aria-labelledby="dspQualityMappingTitle">
          <h3 id="dspQualityMappingTitle">Mapping driver</h3>
          <dl>
            <div><dt>Riconosciuti</dt><dd>${value(counts.mapped_transporters, "0")}</dd></div>
            <div><dt>Da associare</dt><dd>${value(counts.unmapped_transporters, "0")}</dd></div>
            <div><dt>Ambigui</dt><dd>${value(counts.ambiguous_transporters, "0")}</dd></div>
          </dl>
        </section>
      </div>

      <section class="dsp-quality-source" aria-labelledby="dspQualitySourceTitle">
        <h3 id="dspQualitySourceTitle">Fonte</h3>
        <dl>
          <div><dt>File</dt><dd>${value(revision.source_filename)}</dd></div>
          <div><dt>Importata</dt><dd>${importedAt(revision.imported_at)}</dd></div>
          <div><dt>Template</dt><dd>${value(revision.detected_template_version)}</dd></div>
          <div><dt>Revisione attiva</dt><dd>${value(revision.active_number, "1")} di ${value(revision.revision_count, "1")}</dd></div>
        </dl>
      </section>
    </article>
  `;
}


export function qualityAvailableMarkup(view) {
  const section = view.section || "overview";
  return shell(`
    <div class="dsp-quality-available-heading">
      ${view.notice ? `<p class="dsp-quality-notice" role="status">${escapeHtml(view.notice)}</p>` : ""}
      ${view.canImport ? '<button type="button" class="secondary" data-quality-import-open>Importa nuova scorecard</button>' : ""}
    </div>
    <section class="dsp-quality-scorecard-shell" aria-label="Ultima scorecard attiva">
      ${scorecardHistorySelector(view)}
      ${persistedSectionTabs(section)}
      <div class="dsp-quality-section-panel" role="tabpanel">
        ${!view.latest ? '<div class="dsp-quality-selection-loading" role="status" aria-live="polite">Caricamento settimana selezionata…</div>'
          : section === "overview" ? persistedOverview(view.latest)
          : section === "attention" ? qualityAttentionMarkup(view.attention)
          : section === "metrics" ? qualityMetricsMarkup(view.metrics)
          : qualityDriversMarkup(view.drivers)}
      </div>
    </section>
  `);
}


export function qualityLatestErrorMarkup(message) {
  return shell(`
    <div class="dsp-quality-error-state" role="alert">
      <strong>Quality temporaneamente non disponibile</strong>
      <span>${escapeHtml(message || "Impossibile caricare l'ultima scorecard.")}</span>
    </div>
    <button type="button" data-quality-retry>Riprova</button>
  `);
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
        ${[["overview", "Panoramica"], ["attention", "Attenzione"], ["metrics", "Metriche"], ["drivers", "Driver"]].map(([key, label]) => `
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
  if (view.phase === "loading") root.innerHTML = qualityLoadingMarkup();
  else if (view.phase === "empty") root.innerHTML = qualityEmptyMarkup(view.canImport, { hasExisting: Boolean(view.latest?.available) });
  else if (view.phase === "available") root.innerHTML = qualityAvailableMarkup(view);
  else if (view.phase === "preview-loading") root.innerHTML = shell(fileSummary(view.file, "Analisi scorecard in corso…"));
  else if (view.phase === "import-loading") root.innerHTML = shell(`${fileSummary(view.file, "Importazione scorecard in corso…")}${identityMarkup(view.preview)}`);
  else if (view.phase === "preview-ready") root.innerHTML = qualityPreviewMarkup(view);
  else if (view.phase === "success") root.innerHTML = qualitySuccessMarkup(view);
  else if (view.phase === "error" && !view.file) root.innerHTML = qualityLatestErrorMarkup(view.error);
  else root.innerHTML = shell(`
      ${view.canImport ? fileInput() : ""}
      <div class="dsp-quality-error-state" role="alert"><strong>Scorecard non disponibile</strong><span>${escapeHtml(view.error || "Operazione non riuscita.")}</span></div>
      ${view.canImport ? '<button type="button" data-quality-pick>Seleziona un altro PDF</button>' : ""}
    `);
  const identitySource = view.drivers?.reconciliation?.identitySource || {};
  mountSuggestionReview(root, identitySource.review, identitySource.preview);
}

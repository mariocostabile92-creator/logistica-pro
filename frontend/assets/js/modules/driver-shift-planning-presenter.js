import { escapeHtml } from "../utils/dom.js";


const CLASSIFICATION_LABELS = Object.freeze({
  DISTINCT_ASSIGNMENT: "Distinta",
  EXACT_DUPLICATE: "Duplicato esatto",
  POTENTIAL_CONFLICT: "Conflitto",
  IDENTITY_CONFLICT: "Conflitto identità",
  UNRESOLVED_IDENTITY: "Driver non risolto",
});


function safe(value, fallback = "Non disponibile") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}


function dateLabel(value) {
  if (!value) return "Non disponibile";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


function dateTimeLabel(value) {
  if (!value) return "Non disponibile";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}


function provenance(reference) {
  return `${escapeHtml(reference.filename)} · ${escapeHtml(reference.sheet)} · riga ${reference.row_number}`;
}


function alternativeMarkup(alternative, row) {
  const driver = safe(
    alternative.driver_display_name || alternative.source_external_identifier,
    "Driver non risolto",
  );
  const value = [alternative.shift_code, alternative.status_code]
    .filter(Boolean).join(" · ") || "Turno non disponibile";
  const sourceRowId = alternative.source_references?.[0]?.source_row_id;
  return `
    <li>
      <strong>${escapeHtml(driver)}</strong>
      <span>${escapeHtml(value)}</span>
      ${alternative.source_references.map((item) => `<small>${provenance(item)}</small>`).join("")}
      ${row.resolved ? "" : `<button type="button" class="secondary" data-resolve-conflict="${escapeHtml(row.conflict_key)}" data-source-row-id="${sourceRowId}">Usa questa fonte</button>`}
    </li>
  `;
}


function rowMarkup(row, members) {
  const label = CLASSIFICATION_LABELS[row.classification] || row.classification;
  const driver = safe(row.display_name || row.source_external_identifier, "Driver non risolto");
  const hasAlternatives = row.conflicting_alternatives?.length > 0;
  const requiresResolution = [
    "POTENTIAL_CONFLICT", "IDENTITY_CONFLICT", "UNRESOLVED_IDENTITY",
  ].includes(row.classification);
  const memberOptions = members.map((member) => `
    <option value="${member.workforce_member_id}">${escapeHtml(member.display_name)} · ${escapeHtml(member.external_identifier)}</option>
  `).join("");
  const explanation = row.classification === "IDENTITY_CONFLICT"
    ? "Lo stesso T-ID è associato a driver differenti."
    : row.classification === "UNRESOLVED_IDENTITY"
      ? "Associa un membro Workforce oppure escludi la giornata."
      : row.classification === "POTENTIAL_CONFLICT"
        ? "Valori differenti: seleziona esplicitamente la fonte autorevole."
        : row.classification === "EXACT_DUPLICATE"
          ? "Una sola assegnazione candidata, con tutte le fonti conservate."
          : "Assegnazione distinta.";
  return `
    <article class="driver-shift-row ${row.resolved ? "is-resolved" : ""}" data-classification="${escapeHtml(row.classification)}" data-conflict-key="${escapeHtml(row.conflict_key)}">
      <header>
        <div><strong>${escapeHtml(driver)}</strong><span>${escapeHtml(dateLabel(row.operational_date))}</span></div>
        <span class="driver-shift-classification">${escapeHtml(label)}</span>
      </header>
      <dl>
        <div><dt>Turno</dt><dd>${escapeHtml(safe(row.shift_code || row.status_code))}</dd></div>
        <div><dt>T-ID</dt><dd>${escapeHtml(safe(row.transporter_id, "—"))}</dd></div>
        <div><dt>Station</dt><dd>${escapeHtml(safe(row.station, "—"))}</dd></div>
      </dl>
      <p>${escapeHtml(explanation)}</p>
      ${hasAlternatives ? `
        <div class="driver-shift-alternatives" aria-label="Valori sorgente in confronto">
          <span>Valori dalle fonti</span>
          <ul>${row.conflicting_alternatives.map((item) => alternativeMarkup(item, row)).join("")}</ul>
        </div>
      ` : ""}
      <div class="driver-shift-provenance">
        <span>Provenienza</span>
        <ul>${row.source_references.map((item) => `<li>${provenance(item)}</li>`).join("")}</ul>
      </div>
      ${requiresResolution ? `
        <div class="driver-shift-resolution">
          ${row.resolved ? `
            <strong>Risolto: ${escapeHtml(row.resolution?.resolution_type === "EXCLUDE" ? "giornata esclusa" : "fonte selezionata")}</strong>
          ` : row.classification === "UNRESOLVED_IDENTITY" ? `
            <label>Associa a Workforce
              <select data-unresolved-member><option value="">Seleziona driver</option>${memberOptions}</select>
            </label>
            <button type="button" data-resolve-unresolved="${escapeHtml(row.conflict_key)}" data-source-row-id="${row.source_references[0]?.source_row_id}">Associa e usa</button>
          ` : ""}
          ${row.resolved ? "" : `<button type="button" class="quiet" data-exclude-conflict="${escapeHtml(row.conflict_key)}">Escludi questa giornata</button>`}
        </div>
      ` : ""}
    </article>
  `;
}


export function renderPlanningSelector(element, plannings, selectedId) {
  element.hidden = plannings.length <= 1;
  element.innerHTML = plannings.map((item) => `
    <option value="${item.id}" ${item.id === selectedId ? "selected" : ""}>
      ${escapeHtml(item.label || `Planning ${item.id}`)} · ${escapeHtml(dateLabel(item.period_start))}
    </option>
  `).join("");
}


export function renderPlanningHeader(element, planning, sourceCount) {
  if (!planning) { element.innerHTML = ""; return; }
  const badge = planning.status === "ACTIVE" ? "ATTIVO" : planning.status === "SUPERSEDED" ? "SUPERATO" : "BOZZA";
  element.innerHTML = `
    <div>
      <p class="eyebrow">Planning turni</p>
      <h3>${escapeHtml(planning.label || "Planning senza etichetta")}</h3>
      <p>${escapeHtml(dateLabel(planning.period_start))} – ${escapeHtml(dateLabel(planning.period_end))}</p>
    </div>
    <div class="driver-shift-planning-meta">
      <span class="driver-shift-draft-badge" data-status="${escapeHtml(planning.status)}">${badge}</span>
      <span>${sourceCount} ${sourceCount === 1 ? "fonte" : "fonti"}</span>
      <span>v${planning.version}</span>
      <span>Aggiornato ${escapeHtml(dateTimeLabel(planning.updated_at))}</span>
      ${planning.published_at ? `<span>Pubblicato ${escapeHtml(dateTimeLabel(planning.published_at))} da ${escapeHtml(safe(planning.published_by))}</span>` : ""}
    </div>
  `;
}


export function renderSources(element, sources) {
  if (!sources.length) {
    element.innerHTML = '<li class="driver-shift-empty">Nessuna fonte collegata.</li>';
    return;
  }
  element.innerHTML = sources.map((source) => `
    <li class="driver-shift-source-card" data-source-id="${source.id}">
      <div><strong>${escapeHtml(source.source_filename)}</strong><span>Importato ${escapeHtml(dateTimeLabel(source.imported_at))}</span></div>
      <dl>
        <div><dt>Righe</dt><dd>${source.row_count}</dd></div>
        <div><dt>Periodo rilevato</dt><dd>${escapeHtml(dateLabel(source.date_from))} → ${escapeHtml(dateLabel(source.date_to))}</dd></div>
        <div><dt>Compatibilità</dt><dd>${escapeHtml(source.period_compatibility)}</dd></div>
        <div><dt>Merge</dt><dd>${source.status === "AVAILABLE" ? "Disponibile" : "Non disponibile"}</dd></div>
      </dl>
      ${source.warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join("")}
      <button type="button" class="quiet" data-remove-driver-shift-source="${source.id}">Rimuovi dalla combinazione</button>
    </li>
  `).join("");
}


export function renderMergeSummary(element, summary) {
  const values = [
    ["Da risolvere", summary.conflicts_to_resolve],
    ["Risolti", summary.conflicts_resolved],
    ["Identità non risolte", summary.unresolved_identities],
    ["Pronto per pubblicare", summary.ready_to_publish ? "SÌ" : "NO"],
    ["Righe sorgente", summary.total_source_rows],
    ["Righe unificate", summary.unified_rows],
  ];
  element.innerHTML = values.map(([label, value]) => `
    <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value ?? 0))}</dd></div>
  `).join("");
}


export function renderMergeRows(element, preview, members = []) {
  element.innerHTML = preview.rows.length
    ? preview.rows.map((row) => rowMarkup(row, members)).join("")
    : '<p class="driver-shift-empty">Nessuna riga corrisponde ai filtri.</p>';
}


export function renderPagination({ previous, next, status }, preview) {
  const first = preview.filtered_rows ? preview.offset + 1 : 0;
  const last = preview.offset + preview.rows.length;
  status.textContent = `${first}–${last} di ${preview.filtered_rows}`;
  previous.disabled = preview.offset === 0;
  next.disabled = !preview.has_more;
}

import { escapeHtml } from "../utils/dom.js";


const WORKBOOK_LABELS = {
  DAILY_OPERATIONAL_PLANNING: "Planning operativo giornaliero",
  WORKFORCE_SCHEDULE: "Planning turni Workforce",
  FLEET_REGISTRY: "Registro Fleet",
  UNKNOWN_WORKBOOK: "Workbook non riconosciuto",
};


function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}


export function workbookTypeLabel(value) {
  return WORKBOOK_LABELS[value] || WORKBOOK_LABELS.UNKNOWN_WORKBOOK;
}


export function renderSheets(selectEl, profiles, selectedSheet) {
  const automatic = document.createElement("option");
  automatic.value = "";
  automatic.textContent = "Automatico";
  selectEl.replaceChildren(automatic);
  profiles.forEach((sheet) => {
    const option = document.createElement("option");
    option.value = sheet.name;
    option.textContent = `${sheet.name} · ${percent(sheet.score)}`;
    option.selected = sheet.name === selectedSheet;
    selectEl.appendChild(option);
  });
}


export function renderProfile(container, profile) {
  const routed = ["workforce", "fleet_registry"].includes(
    profile.recommended_target,
  );
  const status = profile.import_allowed
    ? "Compatibile"
    : routed
      ? "Riconosciuto e instradato"
      : "Non importabile";
  const tone = profile.import_allowed || routed ? "ok" : "blocked";
  container.innerHTML = `
    <div class="import-profile-heading">
      <div>
        <span class="eyebrow">Struttura rilevata</span>
        <strong>${escapeHtml(workbookTypeLabel(profile.workbook_type))}</strong>
      </div>
      <span class="tag ${tone}">${status}</span>
    </div>
    <dl class="import-profile-facts">
      <div>
        <dt>File</dt>
        <dd>${escapeHtml(profile.original_filename || "Senza nome")}</dd>
      </div>
      <div>
        <dt>Affidabilità tipo</dt>
        <dd>${percent(profile.workbook_type_confidence)}</dd>
      </div>
      <div>
        <dt>Foglio</dt>
        <dd>${escapeHtml(profile.selected_sheet || "Non rilevato")}</dd>
      </div>
      <div>
        <dt>Intestazione</dt>
        <dd>${profile.selected_header_row ? `Riga ${profile.selected_header_row}` : "Non rilevata"}</dd>
      </div>
      <div>
        <dt>Righe dati</dt>
        <dd>${Number(profile.total_rows || 0)}</dd>
      </div>
    </dl>
    <div class="import-profile-summary" aria-label="Riepilogo mapping">
      <span><strong>${profile.recognized_columns.length}</strong> riconosciute</span>
      <span><strong>${profile.ignored_columns.length}</strong> ignorate</span>
      <span><strong>${profile.unknown_columns.length}</strong> da confermare</span>
      <span><strong>${profile.blocking_reasons.length}</strong> blocchi</span>
    </div>
    <p>${escapeHtml(profile.workbook_type_reason)}</p>
    <p class="import-detection-note">
      ${escapeHtml(profile.selected_sheet_reason)}
    </p>
  `;
}


export function renderIssues(container, blockingReasons, warnings) {
  const items = [
    ...blockingReasons.map((item) => ({ ...item, tone: "blocking" })),
    ...warnings.map((item) => ({ ...item, tone: "warning" })),
  ];
  if (!items.length) {
    container.innerHTML = `
      <p class="import-notice ok">
        Struttura compatibile. Controlla il mapping prima dell'import.
      </p>
    `;
    return;
  }
  container.innerHTML = items.map((item) => `
    <p class="import-notice ${item.tone}">
      <strong>${item.tone === "blocking" ? "Da risolvere" : "Attenzione"}:</strong>
      ${escapeHtml(item.message)}
    </p>
  `).join("");
}


export function renderMapping(
  container,
  mappings,
  options,
  { disabled = false } = {},
) {
  if (!mappings.length) {
    container.innerHTML = "";
    return;
  }
  const rows = mappings.map((item) => {
    const initial = item.target_field || (
      item.status === "ignored" ? "__ignore__" : "__unassigned__"
    );
    const optionMarkup = [
      '<option value="__unassigned__">Da confermare</option>',
      '<option value="__ignore__">Ignora colonna</option>',
      ...options.map((option) => `
        <option value="${escapeHtml(option.value)}">
          ${escapeHtml(option.label)}
        </option>
      `),
    ].join("");
    return `
      <label class="mapping-row ${item.status}">
        <span>
          <strong>${escapeHtml(item.source_column)}</strong>
          <small>${percent(item.confidence)} · ${escapeHtml(item.status)}</small>
        </span>
        <select
          data-mapping-source="${escapeHtml(item.source_column)}"
          data-initial-value="${escapeHtml(initial)}"
          aria-label="Destinazione per ${escapeHtml(item.source_column)}"
          ${disabled ? "disabled" : ""}
        >
          ${optionMarkup}
        </select>
      </label>
    `;
  }).join("");
  container.innerHTML = `
    <details class="mapping-details" open>
      <summary>
        <strong>Mapping colonne</strong>
        <span>${mappings.length} colonne rilevate</span>
      </summary>
      <div class="mapping-list">${rows}</div>
    </details>
  `;
  container.querySelectorAll("[data-mapping-source]").forEach((select) => {
    select.value = select.dataset.initialValue;
  });
}


export function collectMapping(container) {
  return [...container.querySelectorAll("[data-mapping-source]")]
    .filter((select) => select.value !== "__unassigned__")
    .map((select) => ({
      source_column: select.dataset.mappingSource,
      target_field: select.value === "__ignore__" ? null : select.value,
    }));
}


export function renderPreview(container, rows) {
  if (!rows.length) {
    container.innerHTML = "<p>Nessuna riga dati disponibile nel campione.</p>";
    return;
  }
  const columns = Object.keys(rows[0]);
  container.innerHTML = `
    <div class="sample-heading">
      <strong>Campione dati</strong>
      <span>Prime ${rows.length} righe utili</span>
    </div>
    <table>
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

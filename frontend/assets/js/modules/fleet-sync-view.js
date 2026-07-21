import { escapeHtml } from "../utils/dom.js";


const ACTION_LABELS = {
  NEW_ASSET: "Nuovo Asset",
  UPDATE_EXISTING: "Aggiornamento",
  NO_CHANGE: "Invariato",
  POSSIBLE_DUPLICATE: "Possibile duplicato",
  CONFLICT: "Conflitto",
  INVALID_ROW: "Riga non valida",
};


export function fleetSyncCounts(items) {
  return items.reduce((counts, item) => {
    counts[item.action] = (counts[item.action] || 0) + 1;
    counts.sensitive += item.sensitive_fields.length;
    return counts;
  }, { sensitive: 0 });
}


export function renderFleetSyncSummary(summary) {
  const facts = [
    ["Nuovi", summary.new_assets],
    ["Aggiornati", summary.updated_assets],
    ["Invariati", summary.unchanged_assets],
    ["Officina", summary.maintenance_assets],
    ["Conflitti", summary.conflicts + summary.possible_duplicates],
    ["Sensibili esclusi", summary.sensitive_fields_excluded],
  ];
  document.getElementById("fleetSyncSummary").innerHTML = facts.map(([label, value]) => `
    <div><span>${escapeHtml(label)}</span><strong>${value}</strong></div>
  `).join("");
}


function stateText(value) {
  if (!value) return "Non presente";
  return [value.plate, value.category, value.availability].filter(Boolean).join(" / ") || "Nessun valore";
}


export function renderFleetSyncDiff(
  container,
  items,
  filter = "ALL",
  selectedRows = new Set(),
) {
  const visible = items.filter((item) => {
    if (filter === "ALL") return true;
    if (filter === "SENSITIVE") return item.sensitive_fields.length > 0;
    return item.action === filter;
  });
  if (!visible.length) {
    container.innerHTML = '<p class="empty-state">Nessuna proposta per questo filtro.</p>';
    return;
  }
  container.innerHTML = visible.map((item) => `
    <article class="fleet-sync-row" data-fleet-sync-action="${item.action}">
      <input
        type="checkbox"
        data-fleet-sync-row="${item.row_id}"
        aria-label="Seleziona riga ${item.excel_row}"
        ${selectedRows.has(item.row_id) ? "checked" : ""}
        ${["CONFLICT", "POSSIBLE_DUPLICATE", "INVALID_ROW"].includes(item.action) ? "disabled" : ""}
      />
      <div>
        <strong>${escapeHtml(item.plate || item.external_identifier || `Riga ${item.excel_row}`)}</strong>
        <small>${escapeHtml(ACTION_LABELS[item.action] || item.action)} - ${Math.round(item.confidence * 100)}%</small>
      </div>
      <div><strong>Stato corrente</strong><span>${escapeHtml(stateText(item.current))}</span></div>
      <div><strong>Stato proposto</strong><span>${escapeHtml(stateText(item.proposed))}</span></div>
      <div>
        <strong>Motivazione</strong><span>${escapeHtml(item.reason)}</span>
        ${item.sensitive_fields.length ? `<small class="fleet-sensitive-notice">Campo sensibile rilevato: escluso dall'import automatico (${item.sensitive_fields.map((field) => escapeHtml(field.column)).join(", ")}).</small>` : ""}
      </div>
    </article>
  `).join("");
}

import { labelForField } from "../utils/formatters.js";
import { escapeHtml } from "../utils/dom.js";


export function renderSheets(selectEl, sheets, selectedSheet) {
  selectEl.innerHTML = '<option value="">Automatico</option>';
  sheets.forEach((sheet) => {
    const option = document.createElement("option");
    option.value = sheet;
    option.textContent = sheet;
    option.selected = sheet === selectedSheet;
    selectEl.appendChild(option);
  });
}


export function renderMapping(container, recognized, unrecognized) {
  const items = [
    ...recognized.map((item) => ({ ...item, ok: true })),
    ...unrecognized.map((column) => ({ source_column: column, target_field: null, confidence: 0, ok: false })),
  ];
  container.innerHTML = items.map((item) => `
    <div class="mapping-item ${item.ok ? "" : "needs-confirmation"}">
      <span>${escapeHtml(item.source_column)}</span>
      <strong>${escapeHtml(labelForField(item.target_field))} (${Math.round(item.confidence * 100)}%)</strong>
    </div>
  `).join("");
}


export function renderPreview(container, rows) {
  if (!rows.length) {
    container.innerHTML = "<p>Nessuna riga disponibile per la preview.</p>";
    return;
  }
  const columns = Object.keys(rows[0]);
  container.innerHTML = `
    <table>
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

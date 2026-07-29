import { escapeHtml } from "../utils/dom.js";
import { severityLabel } from "../utils/formatters.js";


export function renderOperationalIssues(container, issues) {
  container.innerHTML = issues.length ? issues.map((item) => `
    <article class="conflict ${item.severity}">
      <div class="conflict-header">
        <strong>${severityLabel(item.severity)}</strong>
        <span class="conflict-code">${escapeHtml(item.code)}</span>
      </div>
      <p>${escapeHtml(item.description)}</p>
      <p class="issue-reason">${escapeHtml(item.reason)}</p>
      <p>Entità: ${escapeHtml(item.entity_ref)}${item.row_number ? `, riga ${item.row_number}` : ""}</p>
      ${item.suggested_action ? `<p>Azione suggerita: ${escapeHtml(item.suggested_action)}</p>` : ""}
    </article>
  `).join("") : '<div class="empty-state">Nessun problema operativo rilevato.</div>';
}

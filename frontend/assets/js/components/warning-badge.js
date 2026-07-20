import { escapeHtml } from "../utils/dom.js";
import { operationalCodeLabel } from "../utils/formatters.js";


export function warningBadges(warnings = []) {
  if (!warnings.length) return '<span class="section-note">Nessuno</span>';
  return `<div class="warning-list">${warnings
    .map((warning) => `
      <span class="warning-badge" title="${escapeHtml(warning)}">
        ${escapeHtml(operationalCodeLabel(warning))}
      </span>
    `)
    .join("")}</div>`;
}

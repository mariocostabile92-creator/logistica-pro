import { escapeHtml } from "../utils/dom.js";


export function warningBadges(warnings = []) {
  if (!warnings.length) return '<span class="section-note">Nessuno</span>';
  return `<div class="warning-list">${warnings
    .map((warning) => `<span class="warning-badge">${escapeHtml(warning)}</span>`)
    .join("")}</div>`;
}

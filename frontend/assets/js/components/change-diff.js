import { escapeHtml } from "../utils/dom.js";


export function changeDiff(diff) {
  return `
    <div class="change-diff">
      <strong>${escapeHtml(diff.summary)}</strong>
      <ul>
        ${(diff.assignment_changes || []).map((change) => `
          <li>${escapeHtml(change.route_id)}: ${escapeHtml(change.changed_fields.join(", "))}</li>
        `).join("")}
      </ul>
      ${(diff.warnings || []).map((warning) => `<p>${escapeHtml(warning)}</p>`).join("")}
    </div>
  `;
}

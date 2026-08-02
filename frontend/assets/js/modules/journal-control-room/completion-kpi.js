import { escapeHtml } from "../../utils/dom.js";
import { completionKpiGroups } from "./completion-filters.js";

export function completionKpis(completion, activeFilter) {
  return completionKpiGroups.map(group => `<section class="jcr-completion-kpi-group group-${group.key}">
    <h4>${escapeHtml(group.label)}</h4><div>${group.entries.map(([key, label, value]) => `<button type="button"
      class="jcr-completion-kpi ${activeFilter === key ? "active" : ""}"
      data-jcr-completion-filter="${key}" aria-pressed="${activeFilter === key}">
      <strong>${value(completion)}</strong><span>${escapeHtml(label)}</span><small>Filtra</small></button>`).join("")}</div>
  </section>`).join("");
}

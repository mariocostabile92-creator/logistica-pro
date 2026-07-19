import { byId, escapeHtml, setText } from "../utils/dom.js";
import { planningStatusLabel } from "../components/status-chip.js";


export function renderPlanningBoard(data) {
  const { planning, summary, conflicts } = data;
  setText("planningRoutesValue", summary.routes_total);
  setText("planningAssignedValue", summary.routes_assigned);
  setText("planningUnassignedValue", summary.routes_unassigned);
  setText("planningOverridesValue", summary.manual_overrides);
  setText("planningVersion", `Versione ${planning.version}`);
  setText(
    "planningTimestamp",
    `${planning.operation_date} · aggiornato ${new Date(planning.updated_at).toLocaleString("it-IT")}`,
  );
  const chip = byId("planningStatusChip");
  chip.textContent = planningStatusLabel(planning.status);
  chip.className = `planning-status ${planning.status}`;
  byId("recalculatePlanningBtn").disabled = false;
  byId("confirmPlanningBtn").disabled = false;
  byId("exportPlanningBtn").disabled = false;
  setText("planningIssuesCount", conflicts.length);
  byId("planningIssues").innerHTML = conflicts.length
    ? conflicts.map((item) => `
        <article class="planning-issue ${escapeHtml(item.severity)}">
          <strong>${escapeHtml(item.message)}</strong>
          <span>${escapeHtml(item.code)} · ${escapeHtml(item.entity_ref)}</span>
        </article>
      `).join("")
    : '<div class="empty-state">Nessun problema planning rilevato.</div>';
}

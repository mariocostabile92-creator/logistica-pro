import { escapeHtml } from "../utils/dom.js";
import { assignmentStatusChip } from "./status-chip.js";
import { warningBadges } from "./warning-badge.js";


export function assignmentCard(assignment) {
  return `
    <article class="assignment-card ${escapeHtml(assignment.assignment_status)}" data-assignment-id="${assignment.id}">
      <div class="assignment-card-header">
        <div>
          <span class="eyebrow">${escapeHtml(assignment.station)}</span>
          <h4>${escapeHtml(assignment.route_id)}</h4>
        </div>
        ${assignmentStatusChip(assignment.assignment_status)}
      </div>
      <div class="assignment-card-grid">
        <div><span>Driver</span><strong>${escapeHtml(assignment.driver_name || "Non assegnato")}</strong></div>
        <div><span>Mezzo</span><strong>${escapeHtml(assignment.plate || "Non assegnato")}</strong></div>
        <div><span>Cycle/Wave</span><strong>${escapeHtml(assignment.cycle_or_wave || "-")}</strong></div>
        <div><span>Origine</span><strong>${escapeHtml(assignment.assignment_source)}</strong></div>
      </div>
      <div class="assignment-card-warnings">${warningBadges(assignment.warnings)}</div>
      <div class="assignment-actions">
        <button type="button" class="small-action" data-action="edit" data-id="${assignment.id}">Modifica</button>
        <button type="button" class="small-action secondary" data-action="alternatives" data-id="${assignment.id}">Alternative</button>
        <button type="button" class="small-action secondary" data-action="confirm" data-id="${assignment.id}" ${assignment.confirmed || !assignment.driver_id || !assignment.plate ? "disabled" : ""}>Conferma</button>
        <button type="button" class="small-action secondary" data-action="simulate-driver" data-id="${assignment.id}">Assenza</button>
        <button type="button" class="small-action secondary" data-action="simulate-vehicle" data-id="${assignment.id}">Mezzo KO</button>
        <button type="button" class="small-action secondary" data-action="simulate-abort" data-id="${assignment.id}">Abort</button>
      </div>
    </article>
  `;
}

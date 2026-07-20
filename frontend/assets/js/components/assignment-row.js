import { escapeHtml } from "../utils/dom.js";
import { assignmentStatusChip } from "./status-chip.js";
import { warningBadges } from "./warning-badge.js";


function alternatives(assignment) {
  if (!assignment.alternatives?.length) return "0";
  return `${assignment.alternatives.length}`;
}


export function assignmentRow(assignment) {
  return `
    <tr class="${assignment.manual_override ? "manual" : ""}" data-assignment-id="${assignment.id}">
      <td>${escapeHtml(assignment.station)}</td>
      <td><strong>${escapeHtml(assignment.route_id)}</strong></td>
      <td>${escapeHtml(assignment.cycle_or_wave || "-")}</td>
      <td>${escapeHtml(assignment.driver_name || "Non assegnata")}</td>
      <td>${escapeHtml(assignment.plate || "Non assegnato")}</td>
      <td>${assignmentStatusChip(assignment.assignment_status)}</td>
      <td>${escapeHtml(assignment.assignment_source)}</td>
      <td>${warningBadges(assignment.warnings)}</td>
      <td><button type="button" class="small-action secondary" data-action="alternatives" data-id="${assignment.id}">${alternatives(assignment)}</button></td>
      <td>
        <div class="assignment-actions">
          <button type="button" class="small-action" data-action="edit" data-id="${assignment.id}">Modifica</button>
          <button type="button" class="small-action secondary" data-action="confirm" data-id="${assignment.id}" ${assignment.confirmed || !assignment.driver_id || !assignment.plate ? "disabled" : ""}>Conferma</button>
          <button type="button" class="small-action secondary" data-action="simulate-driver" data-id="${assignment.id}">Risorsa assente</button>
          <button type="button" class="small-action secondary" data-action="simulate-vehicle" data-id="${assignment.id}">Asset non disponibile</button>
          <button type="button" class="small-action secondary" data-action="simulate-abort" data-id="${assignment.id}">Annulla Task</button>
        </div>
      </td>
    </tr>
  `;
}

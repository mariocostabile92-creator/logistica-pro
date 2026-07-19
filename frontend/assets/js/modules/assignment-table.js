import { assignmentCard } from "../components/assignment-card.js";
import { assignmentRow } from "../components/assignment-row.js";
import { state } from "../state.js";
import { byId, escapeHtml } from "../utils/dom.js";


function matchesFilters(assignment) {
  const station = byId("assignmentFilterStation").value;
  const status = byId("assignmentFilterStatus").value;
  const driver = byId("assignmentFilterDriver").value.trim().toLowerCase();
  const vehicle = byId("assignmentFilterVehicle").value.trim().toLowerCase();
  const problem = byId("assignmentFilterProblems").value;
  if (station && assignment.station !== station) return false;
  if (status && assignment.assignment_status !== status) return false;
  if (driver && !(assignment.driver_name || "").toLowerCase().includes(driver)) return false;
  if (vehicle && !(assignment.plate || "").toLowerCase().includes(vehicle)) return false;
  if (problem === "critical" && !assignment.warnings.length) return false;
  if (problem === "unassigned" && assignment.driver_id && assignment.plate) return false;
  if (problem === "manual" && !assignment.manual_override) return false;
  return true;
}


function populateSelect(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(allLabel)}</option>${values
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    .join("")}`;
  if (values.includes(current)) select.value = current;
}


export function renderAssignments() {
  const data = state.planningOperational.data;
  if (!data) return;
  const assignments = data.assignments.filter(matchesFilters);
  state.planningOperational.filteredAssignments = assignments;
  byId("assignmentTableBody").innerHTML = assignments.length
    ? assignments.map(assignmentRow).join("")
    : '<tr><td colspan="10">Nessuna assegnazione corrisponde ai filtri.</td></tr>';
  byId("assignmentCards").innerHTML = assignments.length
    ? assignments.map(assignmentCard).join("")
    : '<div class="empty-state">Nessuna assegnazione corrisponde ai filtri.</div>';
}


export function refreshAssignmentFilters(data) {
  populateSelect(
    byId("assignmentFilterStation"),
    [...new Set(data.assignments.map((item) => item.station))].sort(),
    "Tutte",
  );
  populateSelect(
    byId("assignmentFilterStatus"),
    [...new Set(data.assignments.map((item) => item.assignment_status))].sort(),
    "Tutti",
  );
  renderAssignments();
}


export function initAssignmentTable(onAction) {
  [
    "assignmentFilterStation",
    "assignmentFilterStatus",
    "assignmentFilterDriver",
    "assignmentFilterVehicle",
    "assignmentFilterProblems",
  ].forEach((id) => {
    byId(id).addEventListener("input", renderAssignments);
    byId(id).addEventListener("change", renderAssignments);
  });
  ["assignmentTableBody", "assignmentCards"].forEach((id) => {
    byId(id).addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button || button.disabled) return;
      onAction(button.dataset.action, Number(button.dataset.id));
    });
  });
}

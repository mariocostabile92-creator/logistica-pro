import { patchPlanningAssignment } from "../api.js?v=5";
import { state } from "../state.js";
import { byId, escapeHtml, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";


let currentAssignment = null;
let onSavedCallback = null;


function option(value, label, selected = false) {
  return `<option value="${escapeHtml(value || "")}" ${selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}


function populateEditor(assignment) {
  const data = state.planningOperational.data;
  const drivers = [
    { id: assignment.driver_id, name: assignment.driver_name },
    ...data.unused_drivers,
  ].filter((item, index, list) => item.id && list.findIndex((other) => other.id === item.id) === index);
  const vehicles = [
    { id: assignment.vehicle_id, plate: assignment.plate },
    ...data.available_vehicles,
    ...(assignment.alternatives || []),
  ].filter((item, index, list) => item.plate && list.findIndex((other) => other.plate === item.plate) === index);

  byId("editorDriver").innerHTML = option("", "Nessuna Risorsa", !assignment.driver_id)
    + drivers.map((item) => option(item.id, item.name, item.id === assignment.driver_id)).join("");
  byId("editorVehicle").innerHTML = option("", "Nessun mezzo", !assignment.plate)
    + vehicles.map((item) => option(item.plate, item.plate, item.plate === assignment.plate)).join("");
  byId("editorAlternatives").innerHTML = assignment.alternatives?.length
    ? assignment.alternatives.map((item) => `<p>${escapeHtml(item.plate || item.driver_name)} · ${escapeHtml(item.reason)}</p>`).join("")
    : "<p>Nessuna alternativa disponibile.</p>";
}


export function openAssignmentEditor(assignmentId) {
  const data = state.planningOperational.data;
  currentAssignment = data.assignments.find((item) => item.id === assignmentId);
  if (!currentAssignment) return;
  byId("editorAssignmentId").value = currentAssignment.id;
  byId("editorRoute").textContent = currentAssignment.route_id;
  byId("editorNote").value = currentAssignment.notes || "";
  byId("editorConfirm").checked = currentAssignment.confirmed;
  populateEditor(currentAssignment);
  byId("assignmentEditor").showModal();
}


async function saveEditor(overrides = {}) {
  if (!currentAssignment) return;
  const submit = byId("assignmentEditorForm").querySelector('button[type="submit"]');
  setLoading(submit, true, "Salvataggio...");
  try {
    const driverId = byId("editorDriver").value;
    const vehiclePlate = byId("editorVehicle").value;
    const payload = {
      driver_id: driverId || null,
      vehicle_id: vehiclePlate || null,
      plate: vehiclePlate || null,
      remove_driver: !driverId,
      remove_vehicle: !vehiclePlate,
      confirm: byId("editorConfirm").checked,
      manual_override: true,
      note: byId("editorNote").value || null,
      ...overrides,
    };
    await patchPlanningAssignment(currentAssignment.id, payload);
    byId("assignmentEditor").close();
    setMessage("");
    await onSavedCallback?.();
  } catch (error) {
    const presentation = userErrorPresentation("planning.assignment-editor", error);
    setMessage(presentation.message, presentation.tone);
  } finally {
    setLoading(submit, false);
  }
}


export function initAssignmentEditor(onSaved) {
  onSavedCallback = onSaved;
  byId("closeAssignmentEditorBtn").addEventListener("click", () => byId("assignmentEditor").close());
  byId("assignmentEditorForm").addEventListener("submit", (event) => {
    event.preventDefault();
    saveEditor();
  });
  byId("removeDriverBtn").addEventListener("click", () => {
    byId("editorDriver").value = "";
    byId("editorConfirm").checked = false;
  });
  byId("removeVehicleBtn").addEventListener("click", () => {
    byId("editorVehicle").value = "";
    byId("editorConfirm").checked = false;
  });
}

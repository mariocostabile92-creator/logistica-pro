import {
  generatePlanning,
  getLatestPlanning,
  getPlanning,
  patchPlanningAssignment,
  recalculatePlanning,
} from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { initAssignmentEditor, openAssignmentEditor } from "./assignment-editor.js";
import {
  initAssignmentTable,
  refreshAssignmentFilters,
} from "./assignment-table.js";
import {
  initExceptionSimulator,
  startQuickSimulation,
} from "./exception-simulator.js";
import { renderPlanningBoard } from "./planning-board.js";
import { initPlanningExport } from "./planning-export.js";
import { renderPlanningHistory } from "./planning-history.js";
import { renderStationCapacity } from "./station-capacity.js";


export function renderPlanning(data) {
  state.planningOperational.data = data;
  renderPlanningBoard(data);
  renderStationCapacity(data.station_capacity);
  renderPlanningHistory(data.history);
  refreshAssignmentFilters(data);
  if (!byId("planningOperationDate").value) {
    byId("planningOperationDate").value = data.planning.operation_date;
  }
}


async function reloadPlanning() {
  const planningId = state.planningOperational.data?.planning?.id;
  if (!planningId) return;
  renderPlanning(await getPlanning(planningId));
}


async function generateFromLatestImports() {
  const button = byId("generatePlanningBtn");
  setLoading(button, true, "Generazione...");
  try {
    const threshold = Number(byId("planningReserveThreshold").value || 0);
    const data = await generatePlanning({
      operation_date: byId("planningOperationDate").value || null,
      station: byId("planningStation").value.trim() || null,
      configuration: {
        reserve_vehicle_threshold_global: threshold,
      },
    });
    renderPlanning(data);
    setMessage("");
  } catch (error) {
    setMessage(error.message);
  } finally {
    setLoading(button, false);
  }
}


async function recalculateCurrentPlanning() {
  const data = state.planningOperational.data;
  if (!data) return;
  const button = byId("recalculatePlanningBtn");
  setLoading(button, true, "Ricalcolo...");
  try {
    renderPlanning(await recalculatePlanning(data.planning.id));
    setMessage("");
  } catch (error) {
    setMessage(error.message);
  } finally {
    setLoading(button, false);
  }
}


async function confirmValidAssignments() {
  const data = state.planningOperational.data;
  if (!data) return;
  const button = byId("confirmPlanningBtn");
  const candidates = data.assignments.filter(
    (item) => item.driver_id
      && item.plate
      && !item.confirmed
      && !["blocked", "invalidated", "unassigned"].includes(item.assignment_status),
  );
  setLoading(button, true, `Conferma ${candidates.length}...`);
  try {
    for (const assignment of candidates) {
      await patchPlanningAssignment(assignment.id, {
        confirm: true,
        manual_override: assignment.manual_override,
      });
    }
    await reloadPlanning();
    setMessage("");
  } catch (error) {
    setMessage(error.message);
  } finally {
    setLoading(button, false);
  }
}


async function handleAssignmentAction(action, assignmentId) {
  const data = state.planningOperational.data;
  const assignment = data?.assignments.find((item) => item.id === assignmentId);
  if (!assignment) return;
  if (action === "edit" || action === "alternatives") {
    openAssignmentEditor(assignmentId);
    return;
  }
  if (action === "confirm") {
    try {
      await patchPlanningAssignment(assignmentId, {
        confirm: true,
        manual_override: assignment.manual_override,
      });
      await reloadPlanning();
      setMessage("");
    } catch (error) {
      setMessage(error.message);
    }
    return;
  }
  const eventByAction = {
    "simulate-driver": "driver_absent",
    "simulate-vehicle": "vehicle_unavailable",
    "simulate-abort": "route_aborted",
  };
  if (eventByAction[action]) {
    await startQuickSimulation(eventByAction[action], assignment);
  }
}


async function loadLatestPlanningQuietly() {
  try {
    renderPlanning(await getLatestPlanning());
  } catch {
    // The empty state remains visible until the first planning is generated.
  }
}


export function initPlanningPage() {
  byId("generatePlanningBtn").addEventListener("click", generateFromLatestImports);
  byId("recalculatePlanningBtn").addEventListener("click", recalculateCurrentPlanning);
  byId("confirmPlanningBtn").addEventListener("click", confirmValidAssignments);
  initAssignmentTable(handleAssignmentAction);
  initAssignmentEditor(reloadPlanning);
  initExceptionSimulator(async (data) => renderPlanning(data));
  initPlanningExport();
  document.addEventListener("operations:data-imported", () => {
    byId("planningTimestamp").textContent = "Nuovi dati importati. Genera una nuova proposta.";
  });
  loadLatestPlanningQuietly();
}

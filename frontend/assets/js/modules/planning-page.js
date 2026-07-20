import {
  generatePlanning,
  getLatestPlanning,
  getPlanning,
  patchPlanningAssignment,
  recalculatePlanning,
} from "../api.js";
import { state } from "../state.js";
import {
  byId,
  renderViewState,
  setLoading,
  setMessage,
  setText,
  showDataView,
} from "../utils/dom.js";
import {
  isExpectedApiError,
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
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


let hasValidPlanningImport = false;


function setPlanningGenerationAvailable(available) {
  hasValidPlanningImport = Boolean(available);
  state.planning.validImport = hasValidPlanningImport;
  const button = byId("generatePlanningBtn");
  button.disabled = !hasValidPlanningImport;
  if (hasValidPlanningImport) {
    button.removeAttribute("title");
  } else {
    button.title = "Importa prima un Planning operativo giornaliero valido.";
  }
  byId("planningGenerateHint").hidden = hasValidPlanningImport;
}


export function renderPlanning(data) {
  state.planningOperational.data = data;
  byId("planningCommandActions").hidden = false;
  byId("planningActionsHint").hidden = true;
  showDataView("planningViewState", "planningDataView", true);
  renderPlanningBoard(data);
  setPlanningControlsDisabled(false);
  renderStationCapacity(data.station_capacity);
  renderPlanningHistory(data.history);
  refreshAssignmentFilters(data);
  if (!byId("planningOperationDate").value) {
    byId("planningOperationDate").value = data.planning.operation_date;
  }
  document.dispatchEvent(new CustomEvent("planning:availability-changed", {
    detail: { hasPlanning: true },
  }));
}


function setPlanningControlsDisabled(disabled) {
  const controls = [
    byId("recalculatePlanningBtn"),
    byId("confirmPlanningBtn"),
    byId("exportPlanningBtn"),
  ];
  controls.forEach((control) => {
    control.disabled = disabled;
    if (disabled) {
      control.title = "Disponibile dopo la generazione del Planning.";
    } else {
      control.removeAttribute("title");
    }
  });
  byId("planningActionsHint").hidden = !disabled;
}


function renderPlanningLoading() {
  byId("planningCommandActions").hidden = true;
  byId("planningActionsHint").hidden = true;
  showDataView("planningViewState", "planningDataView", false);
  setText("planningTimestamp", "Verifica dell'ultimo planning in corso...");
  setText("planningVersion", "Versione --");
  const chip = byId("planningStatusChip");
  chip.textContent = "Caricamento";
  chip.className = "planning-status neutral";
  setPlanningControlsDisabled(true);
  renderViewState(byId("planningViewState"), {
    state: "loading",
    title: "Caricamento ultimo planning",
  });
}


function renderPlanningEmpty({
  title = "Nessun planning disponibile",
  description = "Importa planning e parco mezzi, poi genera la prima proposta operativa.",
} = {}) {
  state.planningOperational.data = null;
  state.planningOperational.filteredAssignments = [];
  byId("planningCommandActions").hidden = false;
  showDataView("planningViewState", "planningDataView", false);
  setText("planningTimestamp", "Ultimo planning: nessun dato.");
  setText("planningVersion", "Versione --");
  const chip = byId("planningStatusChip");
  chip.textContent = "Nessun dato";
  chip.className = "planning-status neutral";
  setPlanningControlsDisabled(true);
  renderViewState(byId("planningViewState"), {
    state: "empty",
    title,
    description,
    actionLabel: "Apri import dati",
    action: "open-imports",
  });
  document.dispatchEvent(new CustomEvent("planning:availability-changed", {
    detail: { hasPlanning: false },
  }));
}


function renderPlanningFailure() {
  state.planningOperational.data = null;
  byId("planningCommandActions").hidden = true;
  byId("planningActionsHint").hidden = true;
  showDataView("planningViewState", "planningDataView", false);
  setText("planningTimestamp", "Ultimo planning non disponibile.");
  const chip = byId("planningStatusChip");
  chip.textContent = "Non disponibile";
  chip.className = "planning-status critical";
  setPlanningControlsDisabled(true);
  renderViewState(byId("planningViewState"), {
    state: "error",
    title: "Impossibile caricare il planning",
    description: "Il servizio non ha completato il caricamento. Riprova tra poco.",
    actionLabel: "Riprova",
    action: "retry-planning",
  });
  document.dispatchEvent(new CustomEvent("planning:availability-changed", {
    detail: { hasPlanning: false, failed: true },
  }));
}


function showPlanningActionError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


async function reloadPlanning() {
  const planningId = state.planningOperational.data?.planning?.id;
  if (!planningId) return;
  renderPlanning(await getPlanning(planningId));
}


async function generateFromLatestImports() {
  const button = byId("generatePlanningBtn");
  if (!hasValidPlanningImport) {
    setMessage(
      "Importa prima un Planning operativo giornaliero valido.",
      "warning",
    );
    return;
  }
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
    showPlanningActionError("planning.generate", error);
  } finally {
    setLoading(button, false);
    setPlanningGenerationAvailable(hasValidPlanningImport);
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
    showPlanningActionError("planning.recalculate", error);
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
    showPlanningActionError("planning.confirm-all", error);
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
      showPlanningActionError("planning.confirm-assignment", error);
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


async function loadLatestPlanning() {
  renderPlanningLoading();
  try {
    renderPlanning(await getLatestPlanning());
  } catch (error) {
    if (isExpectedApiError(error, { statuses: [404] })) {
      renderPlanningEmpty();
      return;
    }
    reportUnexpectedError("planning.latest", error);
    renderPlanningFailure();
  }
}


export function initPlanningPage() {
  setPlanningGenerationAvailable(false);
  byId("generatePlanningBtn").addEventListener("click", generateFromLatestImports);
  byId("recalculatePlanningBtn").addEventListener("click", recalculateCurrentPlanning);
  byId("confirmPlanningBtn").addEventListener("click", confirmValidAssignments);
  initAssignmentTable(handleAssignmentAction);
  initAssignmentEditor(reloadPlanning);
  initExceptionSimulator(async (data) => renderPlanning(data));
  initPlanningExport();
  byId("planningViewState").addEventListener("click", (event) => {
    const action = event.target.closest("[data-view-action]")?.dataset.viewAction;
    if (action === "retry-planning") loadLatestPlanning();
    if (action === "open-imports") {
      byId("importsDisclosure").open = true;
      byId("importsSection").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  document.addEventListener("operations:data-imported", (event) => {
    if (event.detail?.datasetType === "planning") {
      setPlanningGenerationAvailable(true);
    }
    if (state.planningOperational.data) {
      setText("planningTimestamp", "Nuovi dati importati. Genera una nuova proposta.");
      return;
    }
    renderPlanningEmpty({
      title: "Dati pronti per il planning",
      description: "Completa gli import necessari e genera la prima proposta operativa.",
    });
  });
  document.addEventListener("demo:workspace-changed", () => {
    loadLatestPlanning();
  });
  document.addEventListener("workspace:status-changed", (event) => {
    setPlanningGenerationAvailable(Boolean(event.detail.latest_planning_import));
  });
  document.addEventListener("workspace:reset-completed", () => {
    setPlanningGenerationAvailable(false);
  });
  loadLatestPlanning();
}

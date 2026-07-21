import { getWorkspaceStatus } from "../api.js";
import { byId, setMessage } from "../utils/dom.js";
import {
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
import { renderWorkspaceCard } from "./workspace-card.js";
import { renderWorkspaceHeader } from "./workspace-header.js";
import { initWorkspaceDialogs } from "./workspace-reset-dialog.js";
import {
  applyWorkspaceEvent,
  createWorkspaceState,
  deriveWorkspaceView,
  WORKSPACE_STATES,
} from "./workspace-state.js";


let workspaceState = createWorkspaceState();
let statusRequestId = 0;
let dialogs = null;


function renderWorkspace() {
  const view = deriveWorkspaceView(workspaceState);
  renderWorkspaceHeader(view);
  renderWorkspaceCard(view);
}


function updateWorkspace(event) {
  workspaceState = applyWorkspaceEvent(workspaceState, event);
  if (workspaceState.status?.workspace_state) {
    document.body.dataset.workspaceState = (
      workspaceState.status.workspace_state
    );
  }
  renderWorkspace();
}


async function refreshWorkspaceStatus() {
  const requestId = ++statusRequestId;
  updateWorkspace({ type: "load-started" });
  try {
    const status = await getWorkspaceStatus();
    if (requestId === statusRequestId) {
      updateWorkspace({ type: "load-completed", status });
      document.dispatchEvent(new CustomEvent("workspace:status-changed", {
        detail: status,
      }));
    }
    return status;
  } catch (error) {
    reportUnexpectedError("workspace.status", error);
    const presentation = userErrorPresentation(
      "workspace.status",
      error,
      { fallback: "Stato workspace temporaneamente non disponibile." },
    );
    if (requestId === statusRequestId) {
      updateWorkspace({
        type: "load-failed",
        message: presentation.message,
      });
    }
    return null;
  }
}


function openImports() {
  byId("workspaceMenu").open = false;
  document.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: {
      view: "operations",
      targetId: "importsSection",
    },
  }));
  requestAnimationFrame(() => {
    byId("importsDisclosure").open = true;
    byId("planningFile").focus({ preventScroll: true });
  });
}


async function afterReset(response, { continueToImport }) {
  updateWorkspace({
    type: "load-completed",
    status: {
      workspace_state: WORKSPACE_STATES.EMPTY,
      is_demo: false,
      demo_enabled: workspaceState.status?.demo_enabled || false,
      latest_planning_import: null,
      latest_fleet_import: null,
      task_count: 0,
      asset_count: 0,
      workforce_member_count: 0,
      planning_count: 0,
      briefing_count: 0,
      last_operational_update: null,
      can_reset: false,
      available_actions: ["import_data"],
    },
  });
  document.dispatchEvent(new CustomEvent("workspace:reset-completed", {
    detail: response,
  }));
  document.dispatchEvent(new CustomEvent("demo:workspace-changed", {
    detail: { status: "reset" },
  }));
  await refreshWorkspaceStatus();
  setMessage(
    "Workspace ripristinato. Ora puoi importare nuovi dati.",
    "success",
  );
  if (continueToImport) {
    openImports();
  } else {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "home" },
    }));
  }
}


function currentStatus() {
  return workspaceState.status;
}


function handleWorkspaceAction(event) {
  const button = event.target.closest("[data-workspace-action]");
  if (!button || !currentStatus()) return;
  const action = button.dataset.workspaceAction;
  const status = currentStatus();
  byId("workspaceMenu").open = false;

  if (action === "import") {
    dialogs.openImport(status, button);
  }
  if (action === "load-demo") {
    document.dispatchEvent(new CustomEvent("demo:load-requested"));
  }
  if (action === "reset") {
    dialogs.openReset({
      opener: button,
      intent: "Rimuove i dati operativi e torna alla Home iniziale.",
    });
  }
  if (action === "new-day") {
    dialogs.openReset({
      opener: button,
      importAfterReset: true,
      intent: (
        "Rimuove i dati operativi correnti e prepara il sistema "
        + "per nuovi file."
      ),
    });
  }
}


export function initWorkspaceLifecycle() {
  dialogs = initWorkspaceDialogs({
    onImport: openImports,
    onResetCompleted: afterReset,
  });
  document.addEventListener("click", handleWorkspaceAction);
  document.addEventListener("workspace:reset-requested", (event) => {
    dialogs.openReset({
      opener: event.detail?.opener || document.activeElement,
      intent: "Rimuove tutti i dati operativi del workspace corrente.",
    });
  });
  document.addEventListener("workspace:import-requested", (event) => {
    if (!currentStatus()) return;
    dialogs.openImport(
      currentStatus(),
      event.detail?.opener || document.activeElement,
    );
  });
  for (const eventName of [
    "operations:data-imported",
    "demo:workspace-changed",
    "briefing:changed",
    "fleet:registry-loaded",
  ]) {
    document.addEventListener(eventName, refreshWorkspaceStatus);
  }
  document.addEventListener(
    "workspace:refresh-requested",
    refreshWorkspaceStatus,
  );
  renderWorkspace();
  refreshWorkspaceStatus();
}

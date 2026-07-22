import { getWorkspaceStatus } from "../api.js";
import { byId, setMessage } from "../utils/dom.js";
import {
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
import {
  createSnapshotCache,
  isAbortError,
} from "../utils/snapshot-cache.js";
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
let initialized = false;
let workspaceRefreshScheduled = false;
const workspaceSnapshotCache = createSnapshotCache({ ttlMs: 30000 });


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


export async function refreshWorkspaceStatus({
  force = false,
  preserveCurrent = true,
} = {}) {
  const requestId = ++statusRequestId;
  if (!preserveCurrent || !workspaceState.status) {
    updateWorkspace({ type: "load-started" });
  }
  try {
    const { value: status } = await workspaceSnapshotCache.read(
      ({ signal }) => getWorkspaceStatus({ signal }),
      { force },
    );
    if (requestId === statusRequestId) {
      updateWorkspace({ type: "load-completed", status });
      document.dispatchEvent(new CustomEvent("workspace:status-changed", {
        detail: status,
      }));
    }
    return status;
  } catch (error) {
    if (isAbortError(error)) return null;
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


function invalidateWorkspaceStatus({ refresh = true } = {}) {
  workspaceSnapshotCache.invalidate({ abortRequest: true });
  if (refresh && !workspaceRefreshScheduled) {
    workspaceRefreshScheduled = true;
    queueMicrotask(() => {
      workspaceRefreshScheduled = false;
      refreshWorkspaceStatus({ force: true, preserveCurrent: true });
    });
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
  const emptyStatus = {
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
  };
  workspaceSnapshotCache.write(emptyStatus);
  updateWorkspace({ type: "load-completed", status: emptyStatus });
  document.dispatchEvent(new CustomEvent("workspace:reset-completed", {
    detail: response,
  }));
  document.dispatchEvent(new CustomEvent("demo:workspace-changed", {
    detail: { status: "reset" },
  }));
  await refreshWorkspaceStatus({ force: true, preserveCurrent: true });
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
  if (initialized) return;
  initialized = true;
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
    "workforce:data-imported",
    "demo:workspace-changed",
  ]) {
    document.addEventListener(eventName, () => invalidateWorkspaceStatus());
  }
  document.addEventListener("fleet:registry-loaded", (event) => {
    const observedCount = Number(event.detail?.assetCount);
    const currentCount = Number(workspaceState.status?.asset_count);
    if (Number.isFinite(observedCount) && observedCount !== currentCount) {
      invalidateWorkspaceStatus();
    }
  });
  document.addEventListener(
    "workspace:refresh-requested",
    () => refreshWorkspaceStatus({ force: true, preserveCurrent: true }),
  );
  renderWorkspace();
  refreshWorkspaceStatus({ preserveCurrent: false });
}

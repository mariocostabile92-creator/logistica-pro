import {
  downloadPlanningCsv,
  getDemoWorkspaceStatus,
  loadDemoWorkspace,
  resetDemoWorkspace,
} from "../api.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import {
  isExpectedApiError,
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
import {
  applyDemoWorkspaceEvent,
  createDemoWorkspaceState,
  deriveDemoWorkspaceView,
} from "./demo-workspace-state.js";


let demoState = createDemoWorkspaceState();


function demoHosts() {
  return [...document.querySelectorAll("[data-demo-host]")];
}


function demoCards() {
  return [...document.querySelectorAll("[data-demo-card]")];
}


function setField(card, field, value) {
  card.querySelector(`[data-demo-field="${field}"]`).textContent = value;
}


function localizedTimestamp(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT");
}


function renderSummary(card, summary) {
  setField(card, "version", summary.dataset_version);
  setField(card, "tasks", summary.counts.tasks);
  setField(card, "human-resources", summary.counts.human_resources);
  setField(card, "assets", summary.counts.assets);
  setField(card, "warnings", summary.counts.warnings);
  setField(card, "planning", summary.planning_status || "Non disponibile");
  setField(card, "loaded-at", localizedTimestamp(summary.created_at));
}


function renderDemoWorkspace() {
  const view = deriveDemoWorkspaceView(demoState);
  byId("headerDemoBadge").hidden = !view.active;
  demoHosts().forEach((host) => {
    host.hidden = view.hidden;
  });
  demoCards().forEach((card) => {
    card.classList.toggle("active", view.active);
    card.querySelector("[data-demo-badge]").textContent = view.badge;
    card.querySelector("[data-demo-inactive]").hidden = !view.inactive;
    card.querySelector("[data-demo-loading]").hidden = !view.loading;
    card.querySelector("[data-demo-active]").hidden = !view.active;
    const statusCopy = card.querySelector("[data-demo-status-copy]");
    statusCopy.textContent = view.statusMessage;
    statusCopy.hidden = !view.statusMessage;
    card.querySelector("[data-demo-action='load']").textContent = view.loadLabel;
    if (view.summary) renderSummary(card, view.summary);
  });
}


function updateDemoState(event) {
  demoState = applyDemoWorkspaceEvent(demoState, event);
  renderDemoWorkspace();
}


function notifyWorkspaceChanged(status, summary = null) {
  document.dispatchEvent(new CustomEvent("demo:workspace-changed", {
    detail: { status, summary },
  }));
}


function notifyDemoAvailability(enabled) {
  document.dispatchEvent(new CustomEvent("demo:availability-changed", {
    detail: { enabled },
  }));
}


async function loadDemo() {
  updateDemoState({ type: "operation-started" });
  try {
    const response = await loadDemoWorkspace();
    updateDemoState({
      type: "load-completed",
      summary: response.summary,
    });
    notifyWorkspaceChanged("ready", response.summary);
    setMessage("Demo Workspace pronto.", "success");
  } catch (error) {
    const presentation = userErrorPresentation("demo.load", error, {
      statuses: [400, 409, 422, 500],
      codes: ["DEMO_LOAD_FAILED"],
    });
    updateDemoState({
      type: "operation-failed",
      message: presentation.message,
    });
    setMessage(presentation.message, presentation.tone);
  }
}


async function resetDemo() {
  const submit = byId("confirmDemoResetBtn");
  setLoading(submit, true, "Reset...");
  updateDemoState({ type: "operation-started" });
  try {
    await resetDemoWorkspace();
    byId("demoResetDialog").close();
    updateDemoState({ type: "reset-completed" });
    notifyWorkspaceChanged("reset");
    setMessage("I dati demo sono stati rimossi.", "success");
  } catch (error) {
    const presentation = userErrorPresentation("demo.reset", error, {
      statuses: [400, 409, 422, 500],
      codes: ["DEMO_RESET_FAILED"],
    });
    updateDemoState({
      type: "operation-failed",
      message: presentation.message,
    });
    setMessage(presentation.message, presentation.tone);
  } finally {
    setLoading(submit, false);
  }
}


async function exportDemo(button) {
  const planningId = demoState.summary?.planning_id;
  if (!planningId) return;
  setLoading(button, true, "Export...");
  try {
    await downloadPlanningCsv(planningId);
    setMessage("");
  } catch (error) {
    const presentation = userErrorPresentation("demo.export", error);
    setMessage(presentation.message, presentation.tone);
  } finally {
    setLoading(button, false);
  }
}


async function handleDemoAction(event) {
  const button = event.target.closest("[data-demo-action]");
  if (!button) return;
  const action = button.dataset.demoAction;
  if (action === "load") {
    await loadDemo();
  }
  if (action === "open-operations") {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "operations", targetId: "planningSection" },
    }));
  }
  if (action === "open-fleet") {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "fleet", targetId: "fleetPluginSection" },
    }));
  }
  if (action === "export") {
    await exportDemo(button);
  }
  if (action === "reset") {
    byId("demoResetDialog").showModal();
  }
}


async function inspectDemoWorkspace() {
  try {
    const response = await getDemoWorkspaceStatus();
    notifyDemoAvailability(true);
    updateDemoState({
      type: "status-loaded",
      status: response.status,
      summary: response.summary,
    });
  } catch (error) {
    if (isExpectedApiError(error, { statuses: [404] })) {
      notifyDemoAvailability(false);
      updateDemoState({ type: "disabled" });
      return;
    }
    reportUnexpectedError("demo.status", error);
    updateDemoState({
      type: "operation-failed",
      message: "Stato demo temporaneamente non disponibile.",
    });
  }
}


export function initDemoWorkspace() {
  const template = byId("demoWorkspaceTemplate");
  demoHosts().forEach((host) => {
    host.append(template.content.cloneNode(true));
  });
  document.addEventListener("click", handleDemoAction);
  document.addEventListener("demo:load-requested", loadDemo);
  byId("demoResetForm").addEventListener("submit", (event) => {
    event.preventDefault();
    resetDemo();
  });
  byId("cancelDemoResetBtn").addEventListener("click", () => {
    byId("demoResetDialog").close();
  });
  renderDemoWorkspace();
  inspectDemoWorkspace();
}

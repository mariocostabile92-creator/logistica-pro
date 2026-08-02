import { loadMissionControlSummary } from "./mission-control-api.js?v=4";
import { renderMissionControl } from "./mission-control/renderer.js?v=2";
import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "./mission-control-state.js";


const FLEET_TARGETS = new Set(["library", "journal", "damage", "maintenance", "documents", "vision"]);
let state = createMissionControlState();
let initialized = false;
let request = null;
let refreshQueued = false;


function update(event) {
  state = applyMissionControlEvent(state, event);
  renderMissionControl(deriveMissionControlView(state));
}


async function refreshSummary() {
  if (request) return request;
  update({ type: "summary-loading" });
  request = loadMissionControlSummary()
    .then((summary) => update({ type: "summary-loaded", summary }))
    .catch(() => update({
      type: "summary-failed",
      message: "I riepiloghi operativi non sono temporaneamente disponibili.",
    }))
    .finally(() => { request = null; });
  return request;
}


function scheduleRefresh() {
  if (refreshQueued) return;
  refreshQueued = true;
  window.setTimeout(() => {
    refreshQueued = false;
    refreshSummary();
  }, 250);
}


function openFleetTarget(target) {
  if (target === "library") {
    document.dispatchEvent(new CustomEvent("workspace:navigate", { detail: { view: "fleet" } }));
    return;
  }
  const reveal = (event) => {
    if (event.detail.view !== "fleet") return;
    document.removeEventListener("workspace:view-changed", reveal);
    requestAnimationFrame(() => document.querySelector(`[data-fleet-module="${target}"]`)?.click());
  };
  document.addEventListener("workspace:view-changed", reveal);
  document.dispatchEvent(new CustomEvent("workspace:navigate", { detail: { view: "fleet" } }));
}


function handleNavigation(event) {
  const target = event.target.closest("[data-mission-target]")?.dataset.missionTarget;
  if (!target) return;
  if (FLEET_TARGETS.has(target)) {
    openFleetTarget(target);
    return;
  }
  const view = target === "planning" ? "operations" : target;
  document.dispatchEvent(new CustomEvent("workspace:navigate", { detail: { view } }));
}


export function initMissionControl() {
  if (initialized) return;
  initialized = true;
  document.getElementById("missionControlSection").addEventListener("click", handleNavigation);
  document.addEventListener("briefing:changed", (event) => {
    update({ type: "briefing-loaded", briefing: event.detail.briefing });
  });
  document.addEventListener("workspace:status-changed", (event) => {
    update({ type: "workspace-loaded", workspace: event.detail });
  });
  document.addEventListener("workspace:reset-completed", (event) => {
    update({ type: "workspace-reset", workspace: event.detail || null });
    scheduleRefresh();
  });
  [
    "damage:changed", "maintenance:changed", "documents:changed",
    "journal:changed", "fleet:status-changed", "planning:changed",
  ].forEach((name) => document.addEventListener(name, scheduleRefresh));
  renderMissionControl(deriveMissionControlView(state));
  refreshSummary();
}

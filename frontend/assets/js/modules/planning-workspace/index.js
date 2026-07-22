import { createPlanningWorkspaceLayout } from "./layout.js";
import { renderPlanningWorkspace } from "./renderer.js";
import {
  applyPlanningWorkspaceEvent,
  createPlanningWorkspaceState,
  derivePlanningWorkspaceView,
} from "./state.js";
import { focusRelativeAction } from "./utils.js";


let initialized = false;
let state;
let refs;


function today() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


function commit(event) {
  state = applyPlanningWorkspaceEvent(state, event);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
}


function openLegacyFlow() {
  const legacy = document.getElementById("legacyOperationsRegion");
  const summary = document.getElementById("legacyOperationsSummary");
  legacy.open = true;
  refs.legacyButton.setAttribute("aria-expanded", "true");
  summary.focus({ preventScroll: true });
  legacy.scrollIntoView({ behavior: "smooth", block: "start" });
}


function handleActionClick(event) {
  const action = event.target.closest("[data-planning-action]")?.dataset
    .planningAction;
  if (action === "open-legacy") openLegacyFlow();
}


function handleActionKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  if (event.key === "Home") {
    refs.actions.querySelector("button:not(:disabled)")?.focus();
    return;
  }
  if (event.key === "End") {
    const actions = refs.actions.querySelectorAll("button:not(:disabled)");
    actions[actions.length - 1]?.focus();
    return;
  }
  focusRelativeAction(
    refs.actions,
    event.target,
    event.key === "ArrowRight" ? 1 : -1,
  );
}


function handleLegacyKeydown(event) {
  if (event.key !== "Escape" || !event.currentTarget.open) return;
  event.currentTarget.open = false;
  refs.legacyButton.setAttribute("aria-expanded", "false");
  refs.legacyButton.focus();
}


export function initPlanningWorkspace() {
  if (initialized) return;
  initialized = true;
  const root = document.getElementById("planningWorkspaceRoot");
  state = createPlanningWorkspaceState({ planningDate: today() });
  refs = createPlanningWorkspaceLayout(root);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
  refs.actions.addEventListener("click", handleActionClick);
  refs.actions.addEventListener("keydown", handleActionKeydown);
  document.getElementById("legacyOperationsRegion").addEventListener(
    "keydown",
    handleLegacyKeydown,
  );
  queueMicrotask(() => commit({ type: "legacy-active" }));
}

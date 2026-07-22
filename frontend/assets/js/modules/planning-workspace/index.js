import { getPlanningReadiness } from "../../api.js";
import { createPlanningWorkspaceLayout } from "./layout.js";
import {
  createPlanningReadinessLoader,
  normalizePlanningReadiness,
  readinessEventType,
} from "./readiness.js";
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
const readinessLoader = createPlanningReadinessLoader(getPlanningReadiness);


function today() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


function commit(event) {
  state = applyPlanningWorkspaceEvent(state, event);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
}


async function loadReadiness() {
  commit({ type: "load-started" });
  try {
    const payload = await readinessLoader.load({
      organizationId: "default",
      operationalUnitId: "default",
      planningDate: state.planningDate,
    });
    const readiness = normalizePlanningReadiness(payload);
    commit({
      type: readinessEventType(readiness.status),
      message: readiness.rationale,
      snapshot: { readiness },
      operationalUnit: readiness.operationalUnit,
      planningDate: readiness.planningDate,
    });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "load-failed",
      message: error?.message || "Readiness non disponibile. Riprova.",
    });
  }
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
  if (action === "retry-readiness") loadReadiness();
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
  refs.root.addEventListener("click", handleActionClick);
  refs.actions.addEventListener("keydown", handleActionKeydown);
  document.getElementById("legacyOperationsRegion").addEventListener(
    "keydown",
    handleLegacyKeydown,
  );
  loadReadiness();
}

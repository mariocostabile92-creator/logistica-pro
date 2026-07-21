import { listFleetAssets } from "../api.js";
import { byId } from "../utils/dom.js";
import { reportUnexpectedError } from "../utils/errors.js";
import {
  applyOnboardingEvent,
  createOnboardingState,
  deriveOnboardingView,
} from "./onboarding-state.js";


let onboardingState = createOnboardingState();
let activeWorkspace = "home";


function renderStep(key, completed, active) {
  const item = document.querySelector(`[data-onboarding-step="${key}"]`);
  item.classList.toggle("completed", completed);
  item.classList.toggle("active", active);
  item.classList.toggle("locked", !completed && !active);
  item.querySelector(".onboarding-step-marker").textContent = completed
    ? "\u2713"
    : item.dataset.stepNumber;
  item.querySelector(".onboarding-step-status").textContent = completed
    ? "Completato"
    : active
      ? "Passaggio attivo"
      : "In attesa";
  item.querySelector(".onboarding-step-action").hidden = !active;
}


function renderOnboarding() {
  const view = deriveOnboardingView(onboardingState);
  document.body.dataset.homeState = view.homeState;
  document.body.dataset.planningState = view.loading
    ? "loading"
    : view.steps.planningGenerated
      ? "ready"
      : "empty";
  byId("onboardingSection").hidden = (
    activeWorkspace !== "home" || !view.showOnboarding
  );
  byId("onboardingLoading").hidden = !view.loading;
  byId("onboardingContent").hidden = view.loading;
  byId("onboardingHero").hidden = !view.showHero;
  byId("importsDisclosure").open = !view.steps.planningGenerated;

  renderStep(
    "planning",
    view.steps.planningImported,
    view.activeStep === "planning",
  );
  renderStep(
    "fleet",
    view.steps.fleetImported,
    view.activeStep === "fleet",
  );
  renderStep(
    "generate",
    view.steps.planningGenerated,
    view.activeStep === "generate",
  );
}


function updateOnboarding(event) {
  onboardingState = applyOnboardingEvent(onboardingState, event);
  renderOnboarding();
}


async function inspectFleetRegistry() {
  try {
    const response = await listFleetAssets();
    updateOnboarding({
      type: "fleet-registry-loaded",
      assetCount: response.items.length,
    });
  } catch (error) {
    reportUnexpectedError("onboarding.fleet-registry", error);
    updateOnboarding({
      type: "fleet-registry-loaded",
      assetCount: null,
    });
  }
}


export function initOnboarding() {
  byId("onboardingSection").addEventListener("click", (event) => {
    const action = event.target.closest("[data-onboarding-action]")
      ?.dataset.onboardingAction;
    if (!action) return;
    if (action === "planning") {
      document.dispatchEvent(new CustomEvent("workforce:import-requested"));
      return;
    }
    const targets = {
      fleet: ["importsSection", "fleetFile"],
      generate: ["planningSection", "generatePlanningBtn"],
    };
    const [targetId, focusId] = targets[action];
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "operations", targetId },
    }));
    requestAnimationFrame(() => {
      if (targetId === "importsSection") byId("importsDisclosure").open = true;
      byId(focusId).focus({ preventScroll: true });
    });
  });

  document.addEventListener("planning:availability-changed", (event) => {
    updateOnboarding({
      type: "planning-availability",
      hasPlanning: event.detail.hasPlanning,
    });
  });
  document.addEventListener("operations:data-imported", (event) => {
    updateOnboarding({
      type: "dataset-imported",
      datasetType: event.detail.datasetType,
    });
  });
  document.addEventListener("operations:dashboard-updated", (event) => {
    updateOnboarding({
      type: "dashboard-availability",
      available: event.detail.available,
    });
  });
  document.addEventListener("fleet:registry-loaded", (event) => {
    updateOnboarding({
      type: "fleet-registry-loaded",
      assetCount: event.detail.assetCount,
    });
  });
  document.addEventListener("workspace:status-changed", (event) => {
    updateOnboarding({
      type: "workspace-status",
      workforceMemberCount: event.detail.workforce_member_count,
    });
  });
  document.addEventListener("demo:workspace-changed", (event) => {
    if (event.detail.status === "reset") {
      updateOnboarding({ type: "workspace-reset" });
    }
  });
  document.addEventListener("workspace:view-changed", (event) => {
    activeWorkspace = event.detail.view;
    renderOnboarding();
  });

  renderOnboarding();
  inspectFleetRegistry();
}

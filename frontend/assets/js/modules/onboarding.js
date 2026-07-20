import { listFleetAssets } from "../api.js";
import { byId } from "../utils/dom.js";
import { reportUnexpectedError } from "../utils/errors.js";
import {
  applyOnboardingEvent,
  createOnboardingState,
  deriveOnboardingView,
} from "./onboarding-state.js";


let onboardingState = createOnboardingState();
let activeWorkspace = "operations";


function renderStep(key, completed) {
  const item = document.querySelector(`[data-onboarding-step="${key}"]`);
  item.classList.toggle("completed", completed);
  item.querySelector(".onboarding-step-marker").textContent = completed
    ? "\u2713"
    : item.dataset.stepNumber;
  item.querySelector(".onboarding-step-status").textContent = completed
    ? "Completato"
    : "Da completare";
}


function renderChecklistItem(key, completed) {
  const item = document.querySelector(`[data-onboarding-check="${key}"]`);
  item.classList.toggle("completed", completed);
  item.querySelector(".checklist-marker").textContent = completed
    ? "\u2713"
    : "\u25A1";
}


function renderOnboarding() {
  const view = deriveOnboardingView(onboardingState);
  byId("onboardingSection").hidden = (
    activeWorkspace !== "operations" || !view.showOnboarding
  );
  byId("onboardingLoading").hidden = !view.loading;
  byId("onboardingContent").hidden = view.loading;
  byId("onboardingHero").hidden = !view.showHero;

  renderStep("planning", view.steps.planningImported);
  renderStep("fleet", view.steps.fleetImported);
  renderStep("generate", view.steps.planningGenerated);
  renderChecklistItem("planning", view.checklist.planningImported);
  renderChecklistItem("fleet", view.checklist.fleetImported);
  renderChecklistItem("planning-generated", view.checklist.planningGenerated);
  renderChecklistItem("operational", view.checklist.systemOperational);
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
  byId("startImportBtn").addEventListener("click", () => {
    byId("importsSection").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
    byId("planningFile").focus({ preventScroll: true });
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
  document.addEventListener("workspace:view-changed", (event) => {
    activeWorkspace = event.detail.view;
    renderOnboarding();
  });

  renderOnboarding();
  inspectFleetRegistry();
}

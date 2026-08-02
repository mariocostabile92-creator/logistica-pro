import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyOnboardingEvent,
  createOnboardingState,
  deriveOnboardingView,
} from "../assets/js/modules/onboarding-state.js";


function emptySystemState() {
  let current = createOnboardingState();
  current = applyOnboardingEvent(current, {
    type: "planning-availability",
    hasPlanning: false,
  });
  return applyOnboardingEvent(current, {
    type: "fleet-registry-loaded",
    assetCount: 0,
  });
}


test("first access with an empty database shows hero and incomplete progress", () => {
  const view = deriveOnboardingView(emptySystemState());

  assert.equal(view.loading, false);
  assert.equal(view.showHero, true);
  assert.equal(view.homeState, "setup");
  assert.equal(view.activeStep, "planning");
  assert.deepEqual(view.steps, {
    planningImported: false,
    fleetImported: false,
    planningGenerated: false,
  });
  assert.equal(view.checklist.systemOperational, false);
});


test("planning and fleet imports complete the first two wizard steps", () => {
  let current = emptySystemState();
  current = applyOnboardingEvent(current, {
    type: "dataset-imported",
    datasetType: "planning",
  });
  current = applyOnboardingEvent(current, {
    type: "dataset-imported",
    datasetType: "fleet",
  });
  const view = deriveOnboardingView(current);

  assert.equal(view.showHero, true);
  assert.equal(view.activeStep, "generate");
  assert.equal(view.steps.planningImported, true);
  assert.equal(view.steps.fleetImported, true);
  assert.equal(view.steps.planningGenerated, false);
});


test("Workforce import and persisted members complete Planning turni on Home", () => {
  let imported = emptySystemState();
  imported = applyOnboardingEvent(imported, {
    type: "dataset-imported",
    datasetType: "workforce",
  });
  assert.equal(deriveOnboardingView(imported).steps.planningImported, true);

  let restored = emptySystemState();
  restored = applyOnboardingEvent(restored, {
    type: "workspace-status",
    workforceMemberCount: 173,
  });
  assert.equal(restored.workforceMemberCount, 173);
  assert.equal(deriveOnboardingView(restored).steps.planningImported, true);
});


test("an existing planning restores all wizard prerequisites", () => {
  let current = createOnboardingState({ fleetKnown: true });
  current = applyOnboardingEvent(current, {
    type: "planning-availability",
    hasPlanning: true,
  });
  const view = deriveOnboardingView(current);

  assert.equal(view.steps.planningImported, true);
  assert.equal(view.steps.fleetImported, true);
  assert.equal(view.steps.planningGenerated, true);
  assert.equal(view.showOnboarding, false);
  assert.equal(view.homeState, "ready");
});


test("demo reset immediately restores the empty onboarding state", () => {
  const current = createOnboardingState({
    planningKnown: true,
    fleetKnown: true,
    planningImported: true,
    fleetImported: true,
    planningGenerated: true,
    dashboardAvailable: true,
    assetCount: 11,
  });

  const reset = applyOnboardingEvent(current, {
    type: "workspace-reset",
  });
  const view = deriveOnboardingView(reset);

  assert.equal(view.loading, false);
  assert.equal(view.showHero, true);
  assert.equal(view.activeStep, "planning");
  assert.deepEqual(view.steps, {
    planningImported: false,
    fleetImported: false,
    planningGenerated: false,
  });
  assert.equal(view.checklist.systemOperational, false);
});


test("the onboarding closes after the first Planning is generated", () => {
  let current = createOnboardingState({
    planningKnown: true,
    fleetKnown: true,
    planningImported: true,
    fleetImported: true,
    planningGenerated: true,
  });
  assert.equal(deriveOnboardingView(current).showOnboarding, false);

  current = applyOnboardingEvent(current, {
    type: "dashboard-availability",
    available: true,
  });
  const view = deriveOnboardingView(current);

  assert.equal(view.checklist.systemOperational, true);
  assert.equal(view.showOnboarding, false);
});


test("the legacy onboarding is absent from the definitive Home payload", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

  assert.doesNotMatch(html, /id="onboardingSection"|data-onboarding-action=/);
  assert.match(html, /id="missionControlSection"/);
  assert.match(html, />Learn</);
});

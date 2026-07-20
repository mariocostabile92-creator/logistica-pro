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


test("the page contains the simplified sequential onboarding", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

  assert.match(html, /Benvenuto in Operations Engine/);
  assert.match(
    html,
    /Completa i tre passaggi iniziali per preparare la prima giornata/,
  );
  assert.match(html, /Importa Planning/);
  assert.match(html, /Importa Fleet/);
  assert.match(html, /Genera il primo Planning/);
  assert.match(html, /data-onboarding-action="planning"/);
  assert.match(html, /data-onboarding-action="fleet"/);
  assert.match(html, /data-onboarding-action="generate"/);
  assert.doesNotMatch(html, /Checklist iniziale/);
  assert.match(html, />Learn</);
});

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

  assert.equal(view.showHero, false);
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
});


test("the onboarding closes only when the dashboard is operational", () => {
  let current = createOnboardingState({
    planningKnown: true,
    fleetKnown: true,
    planningImported: true,
    fleetImported: true,
    planningGenerated: true,
  });
  assert.equal(deriveOnboardingView(current).showOnboarding, true);

  current = applyOnboardingEvent(current, {
    type: "dashboard-availability",
    available: true,
  });
  const view = deriveOnboardingView(current);

  assert.equal(view.checklist.systemOperational, true);
  assert.equal(view.showOnboarding, false);
});


test("the page contains the required hero, wizard and checklist copy", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

  assert.match(html, /Benvenuto in Operations Engine/);
  assert.match(html, /Per iniziare importa un Planning e lo stato del tuo parco mezzi\./);
  assert.match(html, /Inizia importazione/);
  assert.match(html, /Import Planning/);
  assert.match(html, /Import Fleet/);
  assert.match(html, /Genera il primo Planning/);
  assert.match(html, /Sistema operativo/);
  assert.match(html, /Getting Started/);
});

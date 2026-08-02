import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "../assets/js/modules/mission-control-state.js";


const summary = {
  updatedAt: "2026-08-02T08:00:00Z",
  partial: false,
  fleet: {
    available: 20, unavailable: 2, maintenance: 1, openDamage: 2,
    criticalDocuments: 3, missingJournal: 6, deadlines: 4,
  },
  maintenance: { urgent: 1, open: 3 },
  planning: { driversAssigned: 18, vehiclesAssigned: 17, conflicts: 1, publication: "draft" },
  recent: Array.from({ length: 10 }, (_, index) => ({
    id: String(index), timestamp: `2026-08-02T0${index % 9}:00:00Z`,
    label: `Evento ${index}`, source: "Operations",
  })),
};


function readyView() {
  const state = applyMissionControlEvent(createMissionControlState(), {
    type: "summary-loaded", summary,
  });
  return deriveMissionControlView(state);
}


test("initial Operations Home renders a non-blocking operational shell", () => {
  const view = deriveMissionControlView(createMissionControlState());
  assert.equal(view.loading, true);
  assert.equal(view.status.label, "Giornata operativa");
  assert.equal(view.priorities.length, 0);
});


test("general status reports objective critical attention", () => {
  const view = readyView();
  assert.equal(view.status.label, "10 criticità richiedono attenzione");
  assert.equal(view.status.tone, "critical");
});


test("priority cards are ordered and route to specialist workspaces", () => {
  const view = readyView();
  assert.deepEqual(view.priorities.slice(0, 4).map((item) => item.target), [
    "journal", "library", "maintenance", "planning",
  ]);
  assert.equal(view.priorities[0].title, "GDB mancanti");
});


test("Fleet summary exposes only the requested operational counters", () => {
  assert.deepEqual(readyView().fleet, summary.fleet);
});


test("Workforce remains explicitly in preparation without an authoritative snapshot", () => {
  const view = readyView();
  assert.equal(view.workforce.available, false);
  assert.equal(view.workforce.status, "Workspace in preparazione");
});


test("Planning presents assignments conflicts and publication without technical internals", () => {
  const view = readyView();
  assert.deepEqual(view.planning, summary.planning);
  assert.equal(view.recent.length, 8);
});


test("partial sources preserve available data", () => {
  const view = deriveMissionControlView(applyMissionControlEvent(createMissionControlState(), {
    type: "summary-loaded", summary: { ...summary, partial: true },
  }));
  assert.equal(view.partial, true);
  assert.equal(view.fleet.available, 20);
});


test("Home contains the mandatory operational hierarchy", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
  const expectedOrder = [
    "missionControlTitle", "operationsHomeStatus", "operationsHomePrioritiesTitle",
    "operationsHomeFleetTitle", "operationsHomeWorkforceTitle", "operationsHomePlanningTitle",
    "operationsHomeDspTitle", "operationsHomeRecentTitle", "operationsHomeQuickTitle",
  ];
  let previous = -1;
  expectedOrder.forEach((marker) => {
    const current = html.indexOf(marker);
    assert.ok(current > previous, `${marker} must preserve Home order`);
    previous = current;
  });
  assert.match(html, /data-mission-target="vision"/);
  assert.match(html, /data-mission-target="journal"/);
  assert.match(html, /data-mission-target="library"/);
  assert.match(html, /data-mission-target="planning"/);
});


test("Home navigation excludes technical source panels", async () => {
  const navigation = await readFile(
    new URL("../assets/js/modules/view-navigation.js", import.meta.url), "utf8",
  );
  assert.match(navigation, /const HOME_SECTIONS = \["missionControlSection"\]/);
  assert.match(navigation, /HOME_SOURCE_SECTIONS = \[[\s\S]*?briefingSection/);
  assert.match(navigation, /\.\.\.HOME_SOURCE_SECTIONS/);
});


test("Mission Control architecture is split into required components", async () => {
  const renderer = await readFile(
    new URL("../assets/js/modules/mission-control/renderer.js", import.meta.url), "utf8",
  );
  for (const component of ["hero", "priority", "fleet", "workforce", "planning", "recent", "quick-actions"]) {
    assert.match(renderer, new RegExp(`\\./${component}\\.js`));
  }
});


test("responsive Home covers desktop tablet and 390 px without fixed canvas", async () => {
  const css = await readFile(new URL("../assets/css/mission-control.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 820px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /operations-home-kpi-grid/);
  assert.doesNotMatch(css, /operations-home-(?:fleet|module)[^{]*\{[^}]*width:\s*\d{4}px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildDspRowActions,
  dispatchDspAction,
  SIGNAL_ACTIONS,
} from "../assets/js/modules/dsp-workspace/actions.js";
import { rowActionsMarkup } from "../assets/js/modules/dsp-workspace/presenter.js";


const DAY = "2026-08-08";
const allowAll = () => true;
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

function row(overrides = {}) {
  return {
    assignment_id: 12,
    operation_date: DAY,
    driver: { workforce_member_id: 91, name: "Mario Rossi" },
    vehicle: { fleet_asset_id: 71, plate: "AA001AA" },
    journal: { available: true },
    damage: { open_cases_count: 0, relevant_case_ids: [] },
    signals: [],
    ...overrides,
  };
}

function actionsFor(value, options = {}) {
  return buildDspRowActions(value, {
    operationDate: DAY,
    canPermission: allowAll,
    ...options,
  });
}

function signalRow(code, overrides = {}) {
  return row({ signals: [{ code, severity: "warning" }], ...overrides });
}

function navigation(action) {
  const target = new EventTarget();
  const events = [];
  for (const name of [
    "workspace:navigate", "planning:open-date", "workforce:driver-open",
    "fleet:vehicle-open", "journal:open", "damage:open",
  ]) target.addEventListener(name, (event) => events.push(event));
  assert.equal(dispatchDspAction(action, target), true);
  const view = events[0].detail.view;
  target.dispatchEvent(new CustomEvent("workspace:view-changed", { detail: { view } }));
  return events;
}


test("signal map sends DRIVER_WITHOUT_VEHICLE to Planning", () => {
  assert.equal(SIGNAL_ACTIONS.DRIVER_WITHOUT_VEHICLE, "planning");
  assert.equal(actionsFor(signalRow("DRIVER_WITHOUT_VEHICLE")).primary.id, "planning");
});

test("DRIVER_NOT_AVAILABLE opens the canonical Workforce driver", () => {
  const selected = actionsFor(signalRow("DRIVER_NOT_AVAILABLE")).primary;
  assert.equal(selected.id, "driver");
  assert.deepEqual(selected.detail, { driverId: 91 });
});

test("VEHICLE_NOT_AVAILABLE opens the canonical Fleet asset", () => {
  const selected = actionsFor(signalRow("VEHICLE_NOT_AVAILABLE")).primary;
  assert.equal(selected.id, "vehicle");
  assert.deepEqual(selected.detail, { assetId: 71 });
});

for (const code of [
  "JOURNAL_CHECKOUT_MISSING", "JOURNAL_CHECKIN_MISSING",
  "JOURNAL_ANOMALY", "JOURNAL_IN_PROGRESS",
]) {
  test(`${code} opens Journal`, () => {
    assert.equal(actionsFor(signalRow(code)).primary.id, "journal");
  });
}

test("one relevant damage opens that exact case", () => {
  const selected = actionsFor(signalRow("OPEN_DAMAGE_CASE", {
    damage: { open_cases_count: 1, relevant_case_ids: [44] },
  })).primary;
  assert.deepEqual(selected.detail, { caseId: 44 });
});

test("multiple damages open a canonical driver and vehicle context", () => {
  const selected = actionsFor(signalRow("OPEN_DAMAGE_CASE", {
    damage: { open_cases_count: 2, relevant_case_ids: [44, 45] },
  })).primary;
  assert.deepEqual(selected.detail, { driverId: 91, vehicleId: 71 });
});

test("HIGH_SEVERITY_DAMAGE opens Danni", () => {
  const selected = actionsFor(signalRow("HIGH_SEVERITY_DAMAGE", {
    damage: { open_cases_count: 1, relevant_case_ids: [44] },
  })).primary;
  assert.equal(selected.id, "damage");
});

test("VEHICLE_BLOCKED_BY_DAMAGE opens Danni", () => {
  const selected = actionsFor(signalRow("VEHICLE_BLOCKED_BY_DAMAGE", {
    damage: { open_cases_count: 1, relevant_case_ids: [44] },
  })).primary;
  assert.equal(selected.id, "damage");
});

test("Planning action preserves DSP operation_date", () => {
  const selected = actionsFor(signalRow("DRIVER_WITHOUT_VEHICLE")).primary;
  assert.deepEqual(selected.detail, { operationDate: DAY });
  const events = navigation(selected);
  assert.equal(events[1].type, "planning:open-date");
  assert.equal(events[1].detail.operationDate, DAY);
});

test("Journal action preserves operation_date and fleet_asset_id", () => {
  const selected = actionsFor(signalRow("JOURNAL_ANOMALY")).primary;
  assert.equal(selected.detail.operationDate, DAY);
  assert.equal(selected.detail.vehicleId, 71);
  const events = navigation(selected);
  assert.equal(events[1].type, "journal:open");
  assert.deepEqual(events[1].detail, {
    operation_date: DAY, vehicle_id: 71, driver_id: 91,
  });
});

test("driver navigation consumes workforce_member_id after SPA transition", () => {
  const target = new EventTarget();
  const events = [];
  target.addEventListener("workspace:navigate", (event) => events.push(event));
  dispatchDspAction(actionsFor(signalRow("DRIVER_NOT_AVAILABLE")).primary, target);
  assert.equal(events[0].detail.view, "workforce");
  assert.equal(events[0].detail.driverId, 91);
});

test("vehicle navigation consumes fleet_asset_id after SPA transition", () => {
  const events = navigation(actionsFor(signalRow("VEHICLE_NOT_AVAILABLE")).primary);
  assert.equal(events[0].detail.view, "fleet");
  assert.deepEqual(events[1].detail, { assetId: 71 });
});

test("single damage navigation dispatches damage:open with caseId", () => {
  const selected = actionsFor(signalRow("OPEN_DAMAGE_CASE", {
    damage: { open_cases_count: 1, relevant_case_ids: [44] },
  })).primary;
  const events = navigation(selected);
  assert.deepEqual(events[1].detail, { caseId: 44 });
});

test("missing canonical vehicle does not expose a false vehicle CTA", () => {
  const result = actionsFor(signalRow("VEHICLE_NOT_AVAILABLE", {
    vehicle: { fleet_asset_id: null, plate: "AA001AA" },
  }));
  assert.equal(result.all.some((item) => item.id === "vehicle"), false);
  assert.equal(result.primary, null);
});

test("missing canonical driver does not expose a false driver CTA", () => {
  const result = actionsFor(signalRow("DRIVER_NOT_AVAILABLE", {
    driver: { workforce_member_id: null, name: "Mario Rossi" },
  }));
  assert.equal(result.all.some((item) => item.id === "driver"), false);
  assert.equal(result.primary, null);
});

test("permission gating removes only the forbidden domains", () => {
  const result = buildDspRowActions(signalRow("DRIVER_NOT_AVAILABLE", {
    damage: { open_cases_count: 1, relevant_case_ids: [44] },
  }), {
    operationDate: DAY,
    canPermission: (permission) => permission === "planning:read",
  });
  assert.deepEqual(result.all.map((item) => item.id), ["planning"]);
  assert.equal(result.primary, null);
});

test("Journal unavailable removes the Journal action", () => {
  const result = actionsFor(signalRow("JOURNAL_CHECKOUT_MISSING", {
    journal: { available: false },
  }));
  assert.equal(result.all.some((item) => item.id === "journal"), false);
  assert.equal(result.primary, null);
});

test("row without signals has no invasive primary CTA", () => {
  const result = actionsFor(row());
  assert.equal(result.primary, null);
  const markup = rowActionsMarkup(row(), { operationDate: DAY, canPermission: allowAll });
  assert.match(markup, /<summary>Dettagli<\/summary>/);
  assert.doesNotMatch(markup, /class="primary"/);
});

test("attention row renders one primary CTA and secondary actions menu", () => {
  const markup = rowActionsMarkup(signalRow("DRIVER_NOT_AVAILABLE"), {
    operationDate: DAY, canPermission: allowAll,
  });
  assert.match(markup, /class="primary"[\s\S]*Apri driver/);
  assert.match(markup, /<summary>Altre azioni<\/summary>/);
});

test("mobile actions have no fixed width and can stack without overflow", async () => {
  const css = await file("assets/css/dsp-workspace.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.dsp-row-actions[\s\S]*min-width: 0/);
  assert.doesNotMatch(css, /\.dsp-row-actions[\s\S]{0,200}width:\s*390px/);
});

test("DSP actions perform navigation only and never call a write API", async () => {
  const source = await file("assets/js/modules/dsp-workspace/actions.js");
  assert.match(source, /workspace:navigate/);
  assert.doesNotMatch(source, /fetch\(|POST|PATCH|PUT|DELETE/);
});

test("SPA navigation does not reload or assign window.location", async () => {
  const source = await file("assets/js/modules/dsp-workspace/actions.js");
  assert.doesNotMatch(source, /location\.|reload\(|window\.open/);
  assert.match(source, /workspace:view-changed/);
});

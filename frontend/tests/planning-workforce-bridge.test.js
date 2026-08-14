import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { renderForecast } from "../assets/js/modules/planning-operations/forecast.js";
import { renderHero } from "../assets/js/modules/planning-operations/hero.js";
import { renderKpis } from "../assets/js/modules/planning-operations/kpi.js";
import { renderOperations } from "../assets/js/modules/planning-operations/renderer.js";
import { renderDayNavigation } from "../assets/js/modules/planning-operations/day-navigation.js";


const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const source = (relative) => readFile(path.join(FRONTEND, relative), "utf8");

const coverage = {
  available: true,
  requirement_covered: false,
  items: [
    { cycle: "NEXT_DAY", segment: null, forecast: 10, requirement: 11, assigned: 8, requirement_gap: 3, reserve: 0, status: "UNDER_FORECAST" },
    { cycle: "SAME_DAY", segment: "A", forecast: 3, requirement: 4, assigned: 4, requirement_gap: 0, reserve: 0, status: "REQUIREMENT_COVERED" },
    { cycle: "SAME_DAY", segment: "B_C", forecast: 4, requirement: 5, assigned: 2, requirement_gap: 3, reserve: 0, status: "UNDER_FORECAST" },
  ],
};

const payload = {
  operation_date: "2026-08-14",
  planning: null,
  summary: {
    routes_forecast: 17,
    requirement: 20,
    drivers_planned: 14,
    routes_definitive: null,
    vehicles_assigned: null,
    requirement_gap: 6,
    conflicts: null,
    routes_incomplete: null,
    blocking_conflicts: null,
    convocations_ready: null,
  },
  workforce: {
    operation_date: "2026-08-14",
    summary: { planned: 14, available: 15, absent: 1, reserves: 2, next_day: 8, same_day: 6, not_set: 0 },
    coverage,
    drivers: [],
  },
  coverage,
  routes: [],
  route_data_available: false,
  vehicle_assignments_available: false,
  lifecycle: { state: "routes_missing", can_confirm: false, can_publish: false, disabled_reason: "Importa le rotte definitive." },
  permissions: { write: true, diagnostics: true },
};


test("operational date is always rendered and selectable", () => {
  const html = `${renderDayNavigation(payload.operation_date)}${renderHero(payload)}`;
  assert.match(html, /data-planning-operation-date/);
  assert.match(html, /2026-08-14/);
  assert.doesNotMatch(html, /Data<\/dt><dd>Non disponibile/);
});


test("Coverage renders forecast requirement assigned gap and reserve for all buckets", () => {
  const html = renderForecast(coverage);
  assert.match(html, /Next Day/);
  assert.match(html, /Same Day A/);
  assert.match(html, /Same Day B-C/);
  assert.match(html, /Requirement \+10%/);
  assert.match(html, /Assegnati/);
  assert.match(html, /Gap requirement/);
  assert.doesNotMatch(html, /Forecast non disponibile/);
});


test("top KPIs preserve real zero and use an em dash only for unavailable data", () => {
  const html = renderKpis({ ...payload.summary, requirement_gap: 0 });
  assert.match(html, /<strong>0<\/strong><span>Gap requirement/);
  assert.match(html, /<strong>—<\/strong><span>Rotte definitive/);
  assert.match(html, /<strong>—<\/strong><span>Mezzi assegnati/);
});


test("missing route and vehicle sources are described without fake zeroes", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload, []);
  assert.match(root.innerHTML, /Rotte definitive non ancora importate/);
  assert.match(root.innerHTML, /Mezzi non ancora assegnati/);
  assert.match(root.innerHTML, /Il Forecast Amazon è un conteggio/);
});


test("Workforce input exposes canonical counts and same-date deep link CTA", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload, []);
  assert.match(root.innerHTML, /14<\/strong> pianificati/);
  assert.match(root.innerHTML, /1<\/strong> assenti/);
  assert.match(root.innerHTML, /data-open-workforce-planning/);
  assert.match(root.innerHTML, /Apri Planning Workforce/);
});


test("legacy lifecycle stays visible but reports its factual disabled reason", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload, []);
  assert.match(root.innerHTML, /Conferma e pubblicazione/);
  assert.match(root.innerHTML, /Importa le rotte definitive\./);
  assert.match(root.innerHTML, /data-planning-lifecycle="confirm" disabled/);
});


test("date changes are API-scoped and synchronize Planning and Workforce context", async () => {
  const api = await source("assets/js/api.js");
  const controller = await source("assets/js/modules/planning-operations/index.js");
  const workspace = await source("assets/js/modules/planning-workspace/index.js");
  assert.match(api, /operation_date/);
  assert.match(controller, /planning_date/);
  assert.match(controller, /planning:date-changed/);
  assert.match(controller, /workforce:open-date/);
  assert.match(controller, /operationDate: state\.selectedOperationalDate/);
  assert.match(workspace, /openPlanningOperationsDate\(normalized\)/);
});


test("Planning bridge remains responsive at tablet and 390px", async () => {
  const css = await source("assets/css/planning-workspace.css");
  assert.match(css, /planning-coverage-buckets/);
  assert.match(css, /planning-workforce-summary/);
  assert.match(css, /@media \(max-width: 1000px\)/);
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /min-height: 44px/);
  assert.doesNotMatch(css, /planning-coverage-buckets[^}]*width:\s*\d{4}px/s);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  addOperationalDays,
  operationalWeek,
  renderDayNavigation,
  renderWeekSummary,
  summarizeOperationalWeek,
  todayOperationalDate,
} from "../assets/js/modules/planning-operations/day-navigation.js";
import { renderForecast } from "../assets/js/modules/planning-operations/forecast.js";
import { renderKpis } from "../assets/js/modules/planning-operations/kpi.js";
import { renderOperations } from "../assets/js/modules/planning-operations/renderer.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const source = (relative) => readFile(path.join(FRONTEND, relative), "utf8");

function payload(operationDate = "2026-08-14", overrides = {}) {
  const coverage = {
    available: true,
    requirement_covered: false,
    items: [
      { cycle: "NEXT_DAY", segment: null, forecast: 239, requirement: 263, assigned: 45, requirement_gap: 218, reserve: 0, status: "UNDER_FORECAST" },
      { cycle: "SAME_DAY", segment: "A", forecast: 20, requirement: 22, assigned: 15, requirement_gap: 7, reserve: 0, status: "UNDER_FORECAST" },
      { cycle: "SAME_DAY", segment: "B_C", forecast: 18, requirement: 20, assigned: 16, requirement_gap: 4, reserve: 0, status: "UNDER_FORECAST" },
    ],
  };
  return {
    operation_date: operationDate,
    planning: null,
    summary: { routes_forecast: 277, requirement: 305, drivers_planned: 78, requirement_gap: 229, routes_definitive: null, vehicles_assigned: null, conflicts: null, routes_incomplete: null, blocking_conflicts: null, convocations_ready: null },
    workforce: { operation_date: operationDate, summary: { planned: 78, available: 78, absent: 1, next_day: 47, same_day: 31, not_set: 0 }, coverage, drivers: [] },
    coverage,
    routes: [],
    route_data_available: false,
    vehicle_assignments_available: false,
    lifecycle: { state: "routes_missing", can_confirm: false, can_publish: false, disabled_reason: "Importa le rotte definitive." },
    permissions: { write: true, diagnostics: true },
    ...overrides,
  };
}

test("default date helper returns today without UTC day drift", () => {
  assert.equal(todayOperationalDate(new Date(2026, 7, 14, 23, 30)), "2026-08-14");
});

test("weekly strip always contains Monday through Sunday", () => {
  assert.deepEqual(operationalWeek("2026-08-14"), ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-15", "2026-08-16"]);
});

test("selected day is explicit and accessible", () => {
  const html = renderDayNavigation("2026-08-14", new Map([["2026-08-14", payload()]]));
  assert.match(html, /data-planning-select-date="2026-08-14"[^>]*aria-selected="true"[^>]*aria-current="date"/);
  assert.match(html, /class="planning-week-day is-selected"/);
});

test("previous day navigation moves one calendar day", () => {
  assert.equal(addOperationalDays("2026-08-14", -1), "2026-08-13");
});

test("next day navigation moves one calendar day", () => {
  assert.equal(addOperationalDays("2026-08-14", 1), "2026-08-15");
});

test("today control is visible beside previous and next", () => {
  const html = renderDayNavigation("2026-08-14");
  assert.match(html, /data-planning-day-jump="previous"/);
  assert.match(html, /data-planning-day-jump="today">Oggi/);
  assert.match(html, /data-planning-day-jump="next"/);
});

test("date picker moves the strip to the containing week", () => {
  assert.equal(operationalWeek("2026-08-17")[0], "2026-08-17");
  assert.equal(operationalWeek("2026-08-17")[6], "2026-08-23");
});

test("primary KPIs are daily and contain no weekly total", () => {
  const html = renderKpis(payload().summary);
  assert.match(html, /277/);
  assert.match(html, /305/);
  assert.match(html, /78/);
  assert.doesNotMatch(html, /settimana/i);
});

test("coverage shows only selected-day buckets and labels the daily total", () => {
  const html = renderForecast(payload().coverage);
  assert.match(html, /Totale della giornata/);
  assert.match(html, /239/);
  assert.match(html, /20/);
  assert.match(html, /18/);
  assert.doesNotMatch(html, /Lun|Mar|Mer|Gio|Ven|Sab|Dom/);
});

test("Workforce card remains scoped to the selected operation date", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload(), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Fonte Workforce canonica per 2026-08-14/);
  assert.match(root.innerHTML, /78<\/strong> pianificati/);
});

test("route import CTA names the selected day", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload(), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Importa rotte del .*14 agosto/i);
});

test("vehicles remain selected-day facts and never become a weekly aggregate", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload(), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Mezzi non ancora assegnati/);
  assert.doesNotMatch(root.innerHTML, /Mezzi settimana/);
});

test("URL and every day change use selectedOperationalDate", async () => {
  const controller = await source("assets/js/modules/planning-operations/index.js");
  assert.match(controller, /selectedOperationalDate/);
  assert.match(controller, /searchParams\.set\("planning_date"/);
  assert.match(controller, /selectOperationalDate\(selectedDay\.dataset\.planningSelectDate\)/);
  assert.doesNotMatch(controller, /state\.operationDate/);
});

test("week summary is collapsed and explicitly secondary", () => {
  const html = renderWeekSummary("2026-08-14", new Map());
  assert.match(html, /^<details/);
  assert.match(html, /Riepilogo settimana/);
  assert.match(html, /Secondario/);
  assert.match(html, /data-load-planning-week/);
});

test("weekly totals are calculated only after all seven days are loaded", () => {
  const weekPayloads = new Map(operationalWeek("2026-08-14").map((date) => [date, payload(date)]));
  const summary = summarizeOperationalWeek("2026-08-14", weekPayloads);
  assert.equal(summary.complete, true);
  assert.equal(summary.forecast, 1939);
  assert.equal(summary.requirement, 2135);
});

test("lifecycle wording makes the selected-day scope explicit", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload(), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Queste azioni riguardano esclusivamente .*14 agosto/i);
  assert.match(root.innerHTML, /Conferma giornata/);
  assert.match(root.innerHTML, /Pubblica giornata/);
});

test("390px rules keep navigation touchable with controlled horizontal scroll", async () => {
  const css = await source("assets/css/planning-workspace.css");
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /planning-week-strip[^}]*overflow-x:\s*auto/s);
  assert.match(css, /planning-day-navigation nav button[^}]*min-height:\s*44px/s);
  assert.doesNotMatch(css, /planning-week-strip[^}]*width:\s*\d{4}px/s);
});

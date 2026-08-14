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
    fleet_capacity: {
      operational_date: operationDate,
      requested_station: null,
      station_scope_applied: false,
      total_vehicles: 158,
      available_vehicles: 124,
      unavailable_vehicles: 28,
      maintenance_vehicles: 1,
      blocked_vehicles: 5,
      unknown_vehicles: 0,
      vehicle_need: null,
      margin: null,
      route_assignments_available: false,
      assigned_vehicles: null,
      routes_without_vehicle: null,
    },
    routes: [],
    route_data_available: false,
    vehicle_assignments_available: false,
    lifecycle: { state: "routes_missing", can_confirm: false, can_publish: false, disabled_reason: "Importa le rotte definitive." },
    permissions: { write: true, diagnostics: true },
    ...overrides,
  };
}

function fleetSnapshot(operationDate, changes = {}) {
  return {
    operational_date: operationDate,
    requested_station: null,
    station_scope_applied: false,
    total_vehicles: 86,
    available_vehicles: 56,
    unavailable_vehicles: 29,
    maintenance_vehicles: 1,
    blocked_vehicles: 0,
    unknown_vehicles: 0,
    vehicle_need: null,
    vehicle_need_status: "NOT_CONFIGURED",
    margin: null,
    missing_requirement_buckets: ["NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C"],
    route_assignments_available: false,
    assigned_vehicles: null,
    routes_without_vehicle: null,
    ...changes,
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

test("Fleet capacity remains selected-day context and route assignment stays separate", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload(), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Capacità flotta/);
  assert.match(root.innerHTML, /124<\/strong><span>Disponibili/);
  assert.match(root.innerHTML, /In attesa delle rotte definitive/);
  assert.doesNotMatch(root.innerHTML, /Mezzi settimana/);
});

test("complete Fleet snapshot stays synchronized between top KPIs and capacity card", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload("2026-08-15", {
    fleet_capacity: fleetSnapshot("2026-08-15", {
      vehicle_need: 92,
      vehicle_need_status: "COMPLETE",
      margin: -36,
      missing_requirement_buckets: [],
    }),
  }), [], { weekPayloads: new Map() });
  assert.equal((root.innerHTML.match(/<strong>92<\/strong>/g) || []).length, 2);
  assert.equal((root.innerHTML.match(/<strong>56<\/strong>/g) || []).length, 2);
  assert.match(root.innerHTML, /Capacità Fleet insufficiente/);
  assert.match(root.innerHTML, /Mancano 36 mezzi/);
  assert.match(root.innerHTML, /<strong>—<\/strong><span>Mezzi assegnati/);
});

test("partial Fleet snapshot updates top KPI and card in the same render cycle", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload("2026-08-15", {
    fleet_capacity: fleetSnapshot("2026-08-15", {
      vehicle_need: 42,
      vehicle_need_status: "PARTIAL",
      margin: 14,
      missing_requirement_buckets: ["NEXT_DAY"],
    }),
  }), [], { weekPayloads: new Map() });
  assert.equal((root.innerHTML.match(/<strong>Almeno 42<\/strong>/g) || []).length, 2);
  assert.match(root.innerHTML, /<strong>56<\/strong><span>Mezzi disponibili/);

  renderOperations(root, payload("2026-08-15", {
    fleet_capacity: fleetSnapshot("2026-08-15", {
      vehicle_need: 92,
      vehicle_need_status: "COMPLETE",
      margin: -36,
      missing_requirement_buckets: [],
    }),
  }), [], { weekPayloads: new Map() });
  assert.doesNotMatch(root.innerHTML, /Almeno 42/);
  assert.equal((root.innerHTML.match(/<strong>92<\/strong>/g) || []).length, 2);
});

test("day change replaces both Fleet KPI values without historical availability claims", () => {
  const root = { innerHTML: "" };
  renderOperations(root, payload("2026-08-14", {
    fleet_capacity: fleetSnapshot("2026-08-14", {
      vehicle_need: 119,
      vehicle_need_status: "COMPLETE",
      margin: -63,
      missing_requirement_buckets: [],
    }),
  }), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Fleet input · 14 agosto/);
  assert.equal((root.innerHTML.match(/<strong>119<\/strong>/g) || []).length, 2);

  renderOperations(root, payload("2026-08-16", {
    fleet_capacity: fleetSnapshot("2026-08-16"),
  }), [], { weekPayloads: new Map() });
  assert.match(root.innerHTML, /Fleet input · 16 agosto/);
  assert.match(root.innerHTML, /Fabbisogno mezzi da configurare/);
  assert.match(root.innerHTML, /stato è quello operativo corrente/);
  assert.doesNotMatch(root.innerHTML, /<strong>119<\/strong>/);
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

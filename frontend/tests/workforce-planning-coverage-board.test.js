import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  planningCoverageBucketKey,
  planningCoverageDays,
  planningCoverageDetails,
  planningCoveragePrimaryMessage,
  planningCoverageStatusLabel,
  planningCoverageWeeklySummary,
} from "../assets/js/modules/workforce-coverage-presenter.js";
import {
  completePlanningCoverageLoad,
  createPlanningCoverageState,
  failPlanningCoverageLoad,
  startPlanningCoverageLoad,
} from "../assets/js/modules/workforce-coverage-state.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

const bucket = (date, cycle, segment, values = {}) => ({
  operational_date: date,
  cycle,
  segment,
  forecast_routes: 10,
  reserve_percentage: 10,
  required_capacity: 11,
  assigned_drivers: 8,
  forecast_gap: 2,
  requirement_gap: 3,
  reserve_drivers: 0,
  coverage_status: "UNDER_FORECAST",
  ...values,
});

function response() {
  const items = [];
  for (let day = 10; day <= 16; day += 1) {
    const date = `2026-08-${day}`;
    items.push(bucket(date, "NEXT_DAY", null));
    items.push(bucket(date, "SAME_DAY", "A"));
    items.push(bucket(date, "SAME_DAY", "B_C"));
  }
  return { date_from: "2026-08-10", date_to: "2026-08-16", items };
}


test("coverage board presenter always creates seven daily cards for a week", () => {
  assert.equal(planningCoverageDays(response()).length, 7);
});


test("each day contains NEXT DAY", () => {
  assert.equal(planningCoverageDays(response())[0].buckets[0].label, "NEXT DAY");
});


test("each day contains SAME DAY A", () => {
  assert.equal(planningCoverageDays(response())[0].buckets[1].label, "SAME DAY A");
});


test("each day contains SAME DAY B-C", () => {
  assert.equal(planningCoverageDays(response())[0].buckets[2].label, "SAME DAY B-C");
});


test("bucket recognition keeps backend cycle and segment semantics", () => {
  assert.equal(planningCoverageBucketKey({ cycle: "NEXT_DAY", segment: null }), "NEXT_DAY");
  assert.equal(planningCoverageBucketKey({ cycle: "SAME_DAY", segment: "A" }), "SAME_DAY_A");
  assert.equal(planningCoverageBucketKey({ cycle: "SAME_DAY", segment: "B_C" }), "SAME_DAY_B_C");
});


test("primary metric is requirement_gap", () => {
  assert.equal(planningCoveragePrimaryMessage(bucket("2026-08-10", "NEXT_DAY", null)), "Mancano 3");
});


test("UNDER_FORECAST has an explicit textual status", () => {
  assert.equal(planningCoverageStatusLabel("UNDER_FORECAST"), "Sotto forecast");
});


test("FORECAST_COVERED has an explicit textual status", () => {
  assert.equal(
    planningCoverageStatusLabel("FORECAST_COVERED"),
    "Forecast coperto · manca requisito +10%",
  );
});


test("REQUIREMENT_COVERED has an explicit textual status", () => {
  assert.equal(planningCoverageStatusLabel("REQUIREMENT_COVERED"), "Requirement coperto");
});


test("NO_FORECAST has an explicit textual status", () => {
  assert.equal(planningCoverageStatusLabel("NO_FORECAST"), "Forecast non disponibile");
});


test("below forecast exposes both authoritative gaps", () => {
  assert.equal(
    planningCoverageDetails(bucket("2026-08-10", "NEXT_DAY", null, { forecast_gap: 6, requirement_gap: 14 })),
    "6 sotto forecast · 14 sotto requirement",
  );
});


test("forecast covered keeps the +10% gap visible", () => {
  const item = bucket("2026-08-10", "NEXT_DAY", null, {
    assigned_drivers: 78,
    forecast_gap: 0,
    requirement_gap: 6,
    coverage_status: "FORECAST_COVERED",
  });
  assert.equal(planningCoveragePrimaryMessage(item), "Mancano 6 al +10%");
  assert.equal(planningCoverageDetails(item), "Forecast coperto");
});


test("zero gap communicates completed coverage", () => {
  assert.equal(planningCoveragePrimaryMessage(bucket("2026-08-10", "NEXT_DAY", null, {
    requirement_gap: 0,
    coverage_status: "REQUIREMENT_COVERED",
  })), "✓ Copertura completata");
});


test("reserve drivers are called scorte", () => {
  assert.equal(planningCoveragePrimaryMessage(bucket("2026-08-10", "NEXT_DAY", null, {
    requirement_gap: 0,
    reserve_drivers: 2,
    coverage_status: "REQUIREMENT_COVERED",
  })), "✓ Copertura completata · +2 scorte");
});


test("no forecast never presents zero over zero", () => {
  const item = bucket("2026-08-10", "SAME_DAY", "A", {
    forecast_routes: null,
    required_capacity: null,
    assigned_drivers: 3,
    forecast_gap: null,
    requirement_gap: null,
    coverage_status: "NO_FORECAST",
  });
  assert.equal(planningCoveragePrimaryMessage(item), "Forecast non disponibile");
  assert.equal(planningCoverageDetails(item), "3 assegnati");
});


test("weekly summary remains separate for all three buckets", () => {
  const summary = planningCoverageWeeklySummary(response());
  assert.deepEqual(summary.map((item) => item.key), ["NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C"]);
  assert.deepEqual(summary.map((item) => item.forecast), [70, 70, 70]);
});


test("weekly summary presents backend values without recalculating requirement", () => {
  const data = response();
  data.items[0].forecast_routes = 76;
  data.items[0].required_capacity = 84;
  const nextDay = planningCoverageWeeklySummary(data)[0];
  assert.equal(nextDay.forecast, 136);
  assert.equal(nextDay.requirement, 150);
});


test("coverage state exposes only the four required lifecycle fields plus UI focus", () => {
  const state = createPlanningCoverageState();
  assert.equal(state.coverageLoading, false);
  assert.equal(state.coverageError, null);
  assert.equal(state.coverageData, null);
  assert.equal(state.coverageLastUpdated, null);
});


test("coverage loading preserves current data until backend confirmation", () => {
  const current = completePlanningCoverageLoad(createPlanningCoverageState(), response(), new Date(0));
  const loading = startPlanningCoverageLoad(current);
  assert.equal(loading.coverageLoading, true);
  assert.equal(loading.coverageData, current.coverageData);
});


test("coverage success updates data and last-updated", () => {
  const timestamp = new Date("2026-08-10T10:00:00Z");
  const state = completePlanningCoverageLoad(createPlanningCoverageState(), response(), timestamp);
  assert.equal(state.coverageData.items.length, 21);
  assert.equal(state.coverageLastUpdated, timestamp);
});


test("coverage error remains local and leaves existing planning data usable", () => {
  const current = completePlanningCoverageLoad(createPlanningCoverageState(), response());
  const failed = failPlanningCoverageLoad(current, new Error("network"));
  assert.equal(failed.coverageLoading, false);
  assert.equal(failed.coverageData, current.coverageData);
  assert.equal(failed.coverageError.message, "network");
});


test("API client calls the authoritative planning coverage endpoint with optional cycle", async () => {
  const api = await source("assets/js/api.js");
  assert.match(api, /function getPlanningCoverage\(dateFrom, dateTo, cycle = ""\)/);
  assert.match(api, /planning\/coverage\?\$\{params\}/);
  assert.match(api, /if \(cycle\) params\.set\("cycle", cycle\)/);
});


test("single edit refreshes board only after save resolves", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /await saveWorkforceDayStatus[\s\S]*?refreshCoverageAfterStatusSave/);
  assert.match(page, /refreshCoverageAfterStatusSave[\s\S]*?planningCoverageBoard\?\.refresh\(\)/);
});


test("multi-day batch triggers one weekly coverage refresh", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /await saveWorkforceDayStatusesBatch\(payload\)[\s\S]*?refreshCoverageAfterStatusSave/);
  assert.doesNotMatch(page, /for\s*\([^)]*result\.items[^)]*\)[\s\S]{0,180}planningCoverageBoard/);
});


test("copy week refreshes through one target calendar load", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /await applyWorkforceWeekCopy[\s\S]*?await loadCalendar\(/);
  assert.match(page, /async function loadCalendar[\s\S]*?planningCoverageBoard\?\.load\(dateFrom, dateTo\)/);
});


test("cycle filtering only changes emphasis and never refetches partial counts", async () => {
  const [page, board] = await Promise.all([
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/modules/workforce-coverage-board.js"),
  ]);
  assert.match(page, /planningCoverageBoard\.setCycleFilter\(event\.target\.value\)/);
  assert.match(board, /class="planning-coverage-bucket[\s\S]*?is-dimmed/);
  assert.match(board, /fetchCoverage\(dateFrom, dateTo\)/);
  assert.doesNotMatch(board, /fetchCoverage\(dateFrom, dateTo, state\.coverageCycleFilter\)/);
});


test("calendar day click focuses the corresponding coverage card", async () => {
  const calendar = await source("assets/js/modules/workforce-calendar-view.js");
  assert.match(calendar, /onDayFocus\(button\.dataset\.workforceDate\)/);
});


test("mobile board uses controlled horizontal snap without page overflow", async () => {
  const css = await source("assets/css/workforce-coverage-board.css");
  assert.match(css, /@media \(max-width: 900px\)[\s\S]*?overflow-x: auto/);
  assert.match(css, /scroll-snap-type: x mandatory/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?calc\(100vw - 54px\)/);
  assert.match(css, /planning-coverage-day-focus[\s\S]*?min-height: 44px/);
});


test("renderer consumes backend gaps and never duplicates +10 percent math", async () => {
  const presenter = await source("assets/js/modules/workforce-coverage-presenter.js");
  assert.match(presenter, /item\.requirement_gap/);
  assert.match(presenter, /item\.forecast_gap/);
  assert.doesNotMatch(presenter, /1\.1|forecast_routes\s*\*|Math\.ceil/);
});

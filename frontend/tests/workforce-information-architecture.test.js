import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  WORKFORCE_SECTIONS,
  nextWorkforceSection,
  normalizeWorkforceSection,
  workforceSectionFromLocation,
  writeWorkforceSection,
} from "../assets/js/modules/workforce-section-navigation.js";


const root = new URL("../", import.meta.url);
const source = async (path) => readFile(new URL(path, root), "utf8");


test("Workforce defaults to Pianifica and normalizes unknown sections", () => {
  assert.equal(normalizeWorkforceSection(), WORKFORCE_SECTIONS.PLANNING);
  assert.equal(normalizeWorkforceSection("unknown"), WORKFORCE_SECTIONS.PLANNING);
  assert.equal(
    workforceSectionFromLocation({ href: "https://operations.test/app/" }),
    WORKFORCE_SECTIONS.PLANNING,
  );
});


test("Workforce section state supports People, Data and browser history", () => {
  const calls = [];
  const history = {
    state: { existing: true },
    pushState: (...args) => calls.push(["push", ...args]),
    replaceState: (...args) => calls.push(["replace", ...args]),
  };
  assert.equal(writeWorkforceSection("people", {
    history,
    location: { href: "https://operations.test/app/?foo=1" },
  }), "people");
  assert.match(String(calls[0][3]), /foo=1&workforce=people/);
  writeWorkforceSection("data", {
    mode: "replace",
    history,
    location: { href: "https://operations.test/app/" },
  });
  assert.equal(calls[1][0], "replace");
  assert.equal(workforceSectionFromLocation({
    href: "https://operations.test/app/?workforce=data",
  }), "data");
});


test("Workforce section tabs expose keyboard navigation", () => {
  assert.equal(nextWorkforceSection("planning", "ArrowRight"), "people");
  assert.equal(nextWorkforceSection("people", "ArrowRight"), "data");
  assert.equal(nextWorkforceSection("data", "ArrowRight"), "planning");
  assert.equal(nextWorkforceSection("people", "Home"), "planning");
  assert.equal(nextWorkforceSection("people", "End"), "data");
});


test("Workforce HTML defines three accessible internal modes", async () => {
  const html = await source("index.html");
  for (const [section, label] of [
    ["planning", "Pianifica"],
    ["people", "Persone"],
    ["data", "Dati &amp; Import"],
  ]) {
    assert.match(html, new RegExp(`role="tab"[^>]*data-workforce-section="${section}"[^>]*>${label}`));
    assert.match(html, new RegExp(`data-workforce-mode-surface="${section}"`));
  }
  assert.match(html, /id="workforcePlanningModeTab"[\s\S]*?aria-selected="true"/);
  assert.match(html, /id="workforcePeopleModeTab"[\s\S]*?aria-selected="false"/);
  assert.match(html, /id="workforceDataModeTab"[\s\S]*?aria-selected="false"/);
});


test("Pianifica owns Coverage, day planner and calendar first", async () => {
  const [html, page] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(html, /id="planningCoverageBoard"/);
  assert.match(html, /id="workforceDayPlannerOpen"[^>]*>Pianifica giornata/);
  assert.match(page, /planningSurface\.append\(\.\.\.planningNodes\)/);
  assert.match(page, /byId\("workforceCalendarPanel"\)/);
  assert.match(page, /activeWorkforceSection === WORKFORCE_SECTIONS\.PLANNING/);
});


test("People owns compact drivers and the full profile action", async () => {
  const [card, page] = await Promise.all([
    source("assets/js/modules/workforce-availability/availability-card.js"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(card, /Vedi \/ Modifica/);
  assert.doesNotMatch(card, /Abilitazioni/);
  assert.doesNotMatch(card, /consecutivityCard/);
  assert.match(page, /peopleSurface\.append\(document\.querySelector\("\.workforce-foundation"\)\)/);
  assert.match(page, /setWorkforceSection\(WORKFORCE_SECTIONS\.PEOPLE/);
});


test("Data & Import groups sources, merge and contact coverage", async () => {
  const [html, page] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  for (const label of ["A. Import", "B. Fonti Planning", "C. Merge / conflitti", "D. Copertura contatti", "E. Storico / revisioni"]) {
    assert.match(html, new RegExp(label));
  }
  assert.match(page, /dataSources\.append\(byId\("driverShiftPlanningSection"\)\)/);
  assert.match(page, /contactGroup\.append\(byId\("workforceContactCoverage"\)\)/);
});


test("Heavy People and Data reads are lazy and Planning no longer loads them", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  const calendarStart = page.indexOf("async function loadCalendar");
  const calendarEnd = page.indexOf("async function refresh", calendarStart);
  const calendarBody = page.slice(calendarStart, calendarEnd);
  assert.doesNotMatch(calendarBody, /getWorkforceFoundation|getWorkforceContactCoverage|driverShiftPlanning\.refresh/);
  assert.match(page, /async function loadPeopleSectionData[\s\S]*getWorkforceFoundation/);
  assert.match(page, /async function loadDataSectionData[\s\S]*getWorkforceContactCoverage\(\)[\s\S]*driverShiftPlanning\.refresh\(\)/);
});


test("Edit turni uses a single focused context", async () => {
  const [page, css] = await Promise.all([
    source("assets/js/modules/workforce-page.js"),
    source("assets/css/workforce-information-architecture.css"),
  ]);
  assert.match(page, /workforce-editing-shifts/);
  assert.match(page, /workforceDetailPanel\?\.close/);
  assert.match(css, /\.workforce-editing-shifts \.planning-coverage-board/);
  assert.match(css, /\.workforce-editing-shifts \.workforce-command-bar/);
});


test("DSP date and driver deep links select the correct Workforce mode", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /workforce:open-date[\s\S]*WORKFORCE_SECTIONS\.PLANNING/);
  assert.match(page, /openWorkforceDriver[\s\S]*WORKFORCE_SECTIONS\.PEOPLE/);
  assert.match(page, /window\.addEventListener\("popstate"/);
});


test("ordinary rest is not an operational anomaly", async () => {
  const insights = await import("../assets/js/modules/workforce-insights-view.js");
  const result = insights.workforceAnomalies([
    { workforce_member_id: 1, date: "2026-08-10", status_code: "rest" },
    { workforce_member_id: 1, date: "2026-08-11", status_code: "unknown" },
  ], [{ workforce_member_id: 1, display_name: "Mario Rossi" }]);
  assert.equal(result.total, 1);
  assert.equal(result.items[0].category, "unknown");
  assert.equal("rest" in result.counts, false);
});


test("responsive Workforce modes have 44px touch targets and no page overflow", async () => {
  const css = await source("assets/css/workforce-information-architecture.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /\.workforce-section-nav button \{[\s\S]*min-height: 44px/);
  assert.match(css, /\.workforce-data-group \{[\s\S]*overflow: hidden/);
  assert.match(css, /width: 100%/);
});

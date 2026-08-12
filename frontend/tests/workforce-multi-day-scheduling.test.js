import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { workforceCalendarDates } from "../assets/js/modules/workforce-calendar-view.js";
import {
  nextMultiDaySelection,
  workforceBulkChoices,
  workforceBulkPayload,
  workforceNavigationDays,
  workforceQuickSelection,
  workforceQuickSelectionActive,
} from "../assets/js/modules/workforce-multi-day-editor.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("week view always renders Monday through Sunday even with one stored day", () => {
  const statuses = [{ date: "2026-12-28", status_code: "scheduled" }];
  assert.deepEqual(
    workforceCalendarDates(statuses, "week", "2026-12-28", "2027-01-03"),
    [
      "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
      "2027-01-01", "2027-01-02", "2027-01-03",
    ],
  );
  assert.deepEqual(
    workforceCalendarDates([], "day", "2026-12-28", "2026-12-28"),
    ["2026-12-28"],
  );
});


test("multi-day selection toggles cells and shift-click selects a range", () => {
  const visible = ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"];
  let result = nextMultiDaySelection(new Set(), visible[0], visible);
  assert.deepEqual([...result.selectedDates], [visible[0]]);
  result = nextMultiDaySelection(result.selectedDates, visible[0], visible, {
    anchorDate: result.anchorDate,
  });
  assert.equal(result.selectedDates.size, 0);
  result = nextMultiDaySelection(new Set([visible[0]]), visible[4], visible, {
    shiftKey: true,
    anchorDate: visible[0],
  });
  assert.deepEqual([...result.selectedDates], visible);
});


test("quick selection chooses weekdays weekend or the complete visible week", () => {
  const week = [
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-14", "2026-08-15", "2026-08-16",
  ];
  assert.deepEqual([...workforceQuickSelection(new Set(), week, "weekdays")], week.slice(0, 5));
  assert.deepEqual([...workforceQuickSelection(new Set(), week, "weekend")], week.slice(5));
  assert.deepEqual([...workforceQuickSelection(new Set(), week, "week")], week);
});


test("quick selection toggles only when it exactly matches the current selection", () => {
  const week = [
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-14", "2026-08-15", "2026-08-16",
  ];
  const weekdays = workforceQuickSelection(new Set(), week, "weekdays");
  assert.equal(workforceQuickSelectionActive(weekdays, week, "weekdays"), true);
  assert.equal(workforceQuickSelection(weekdays, week, "weekdays").size, 0);
  const partial = new Set(weekdays);
  partial.delete("2026-08-12");
  assert.deepEqual([...workforceQuickSelection(partial, week, "weekdays")], week.slice(0, 5));
});


test("manual selection remains composable after a quick selection", () => {
  const week = [
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-14", "2026-08-15", "2026-08-16",
  ];
  const weekdays = workforceQuickSelection(new Set(), week, "weekdays");
  const result = nextMultiDaySelection(weekdays, "2026-08-12", week);
  assert.deepEqual([...result.selectedDates], [
    "2026-08-10", "2026-08-11", "2026-08-13", "2026-08-14",
  ]);
});


test("bulk catalog reuses imported shift codes and existing status vocabulary", () => {
  const choices = workforceBulkChoices([
    { status_code: "scheduled", shift_code: "SB" },
    { status_code: "rest", shift_code: "R" },
    { status_code: "scheduled", shift_code: "C1" },
    { status_code: "scheduled", shift_code: "SA" },
  ]);
  assert.deepEqual(choices.slice(0, 3).map((item) => item.label), ["C1", "SA", "SB"]);
  assert.ok(choices.some((item) => item.value === "status:rest" && item.label === "Riposo"));
  assert.ok(choices.some((item) => item.value === "status:holiday" && item.label === "Ferie"));
  assert.ok(choices.some((item) => item.value === "status:sickness" && item.label === "Malattia"));
  assert.ok(choices.some((item) => item.value === "status:leave" && item.label === "Permesso"));
  assert.ok(choices.some((item) => item.value === "status:unknown" && item.label === "Da verificare"));
});


test("one payload applies one value to only the selected dates and canonical driver", () => {
  assert.deepEqual(
    workforceBulkPayload(42, new Set(["2026-08-14", "2026-08-10"]), "shift:C1"),
    {
      workforce_member_id: 42,
      dates: ["2026-08-10", "2026-08-14"],
      status_code: "scheduled",
      shift_code: "C1",
      source_reference: "manual_bulk",
    },
  );
  assert.equal(workforceBulkPayload(0, new Set(["2026-08-10"]), "shift:C1"), null);
  assert.equal(workforceBulkPayload(42, new Set(), "shift:C1"), null);
});


test("week navigation moves seven days while day mode moves one", () => {
  assert.equal(workforceNavigationDays("week", -1), -7);
  assert.equal(workforceNavigationDays("week", 1), 7);
  assert.equal(workforceNavigationDays("day", -1), -1);
  assert.equal(workforceNavigationDays("day", 1), 1);
});


test("driver-first UI exposes selection action bar, cancel and one batch apply", async () => {
  const [html, page, calendar, api] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/modules/workforce-calendar-view.js"),
    source("assets/js/api.js"),
  ]);
  for (const id of [
    "workforceMultiDayBar", "workforceMultiDayCount", "workforceMultiDayChoice",
    "workforceMultiDayCancel", "workforceMultiDayApply", "workforceQuickSelection",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /data-workforce-quick-selection="weekdays"[^>]*>Lun–Ven/);
  assert.match(html, /data-workforce-quick-selection="weekend"[^>]*>Weekend/);
  assert.match(html, /data-workforce-quick-selection="week"[^>]*>Tutta la settimana/);
  assert.match(calendar, /data-workforce-member-schedule/);
  assert.match(calendar, /onToggleMultiDayDate/);
  assert.match(page, /saveWorkforceDayStatusesBatch\(payload\)/);
  assert.match(page, /clearMultiDayEditing\(\{ restoreFocus: true \}\)/);
  assert.match(api, /\/day-status\/batch/);
  assert.doesNotMatch(page, /for\s*\([^)]*selectedDates[^)]*\)[\s\S]{0,160}saveWorkforceDayStatus/);
});


test("quick selection stays scoped to the editing driver and resets on week change", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /if \(!multiDayMember\(\) \|\| viewMode !== "week"\) return/);
  assert.match(page, /multiDayEditing\.selectedDates = workforceQuickSelection/);
  assert.doesNotMatch(page, /applyQuickSelection[\s\S]{0,500}memberId\s*=/);
  assert.match(page, /async function loadCalendar[\s\S]{0,300}clearMultiDayEditing\(\{ rerender: false \}\)/);
});


test("quick shortcuts are hidden outside week mode and never apply a shift", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /quickSelection\.hidden = viewMode !== "week"/);
  assert.match(page, /function applyQuickSelection[\s\S]{0,500}renderData\(\)/);
  assert.doesNotMatch(page, /function applyQuickSelection[\s\S]{0,500}saveWorkforceDayStatusesBatch/);
});


test("selection is visible beyond color and mobile action bar has no overflow", async () => {
  const css = await source("assets/css/workforce-calendar.css");
  assert.match(css, /\.workforce-status-button\.is-multi-selected[\s\S]*?outline:/);
  assert.match(css, /\.workforce-status-button\.is-multi-selected::after[\s\S]*?content: "\\2713"/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /max-height: calc\(100vh - 90px\)/);
  assert.match(css, /overflow-y: auto/);
  assert.match(css, /\.workforce-quick-selection-actions button[\s\S]*?min-height: 44px/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?\.workforce-quick-selection-actions[\s\S]*?repeat\(2, minmax\(0, 1fr\)\)/);
});


test("today and date picker open the normalized week while day mode remains explicit", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /workforceTodayBtn[\s\S]{0,100}?loadFromAnchor\(isoDate\(new Date\(\)\)\)/);
  assert.match(page, /workforceDatePicker[\s\S]{0,120}?loadFromAnchor\(event\.target\.value\)/);
  assert.match(page, /if \(viewMode === "day"\) return \{ dateFrom: anchor, dateTo: anchor \}/);
  assert.match(page, /if \(viewMode === "week"\) return periodForAnchor\(fallback\.dateFrom\)/);
});

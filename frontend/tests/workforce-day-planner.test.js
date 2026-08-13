import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  clearWorkforcePlanningSelection,
  createWorkforceDayPlannerState,
  focusWorkforcePlanningDay,
  toggleWorkforcePlanningMember,
} from "../assets/js/modules/workforce-day-planner-state.js";
import {
  filterWorkforceDayMembers,
  workforceCoverageImpact,
  workforceDayBatchPayload,
  workforceDayCounts,
  workforceDayExitWarning,
  workforceWeekProgress,
} from "../assets/js/modules/workforce-day-planner-presenter.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const date = "2026-08-17";
const members = [
  { workforce_member_id: 1, display_name: "Alban Beqiraj", external_identifier: "T-001", operational_cycle: "NEXT_DAY" },
  { workforce_member_id: 2, display_name: "Sara Blu", external_identifier: "T-002", operational_cycle: "SAME_DAY" },
  { workforce_member_id: 3, display_name: "No Cycle", external_identifier: "T-003", operational_cycle: "NOT_SET" },
];
const statuses = [
  { workforce_member_id: 1, date, status_code: "scheduled", shift_code: "C1", operational_activity: "Consegna DLO2", availability: true },
  { workforce_member_id: 2, date, status_code: "rest", shift_code: null, operational_activity: null, availability: false },
];


function coverage(nextDay = {}) {
  const bucket = (cycle, segment, values = {}) => ({
    operational_date: date,
    cycle,
    segment,
    forecast_routes: 10,
    required_capacity: 11,
    assigned_drivers: 8,
    forecast_gap: 2,
    requirement_gap: 3,
    reserve_drivers: 0,
    coverage_status: "UNDER_FORECAST",
    ...values,
  });
  return {
    date_from: date,
    date_to: "2026-08-23",
    items: [
      bucket("NEXT_DAY", null, nextDay),
      bucket("SAME_DAY", "A"),
      bucket("SAME_DAY", "B_C"),
    ],
  };
}


test("day-first state focuses one date and clears unapplied selection", () => {
  let state = createWorkforceDayPlannerState(date);
  state = toggleWorkforcePlanningMember(state, 1);
  assert.equal(state.selectedMemberIds.size, 1);
  state = focusWorkforcePlanningDay(state, "2026-08-18");
  assert.equal(state.focusedDate, "2026-08-18");
  assert.equal(state.selectedMemberIds.size, 0);
});


test("multi-select toggles multiple drivers in the same day", () => {
  let state = createWorkforceDayPlannerState(date);
  state = toggleWorkforcePlanningMember(state, 1);
  state = toggleWorkforcePlanningMember(state, 2);
  assert.deepEqual([...state.selectedMemberIds], [1, 2]);
  state = toggleWorkforcePlanningMember(state, 1);
  assert.deepEqual([...state.selectedMemberIds], [2]);
  assert.equal(clearWorkforcePlanningSelection(state).selectedMemberIds.size, 0);
});


test("cycle filters preserve NEXT DAY, SAME DAY and NOT SET semantics", () => {
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { cycleFilter: "NEXT_DAY" }).map((item) => item.workforce_member_id), [1]);
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { cycleFilter: "SAME_DAY" }).map((item) => item.workforce_member_id), [2]);
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { cycleFilter: "NOT_SET" }).map((item) => item.workforce_member_id), [3]);
});


test("assignment and absence filters use only the focused day", () => {
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { assignmentFilter: "assigned" }).map((item) => item.workforce_member_id), [1]);
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { assignmentFilter: "unassigned" }).map((item) => item.workforce_member_id), [2, 3]);
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { assignmentFilter: "rest" }).map((item) => item.workforce_member_id), [2]);
});


test("cycle and assignment filters combine for dispatcher workflow", () => {
  assert.deepEqual(
    filterWorkforceDayMembers(members, statuses, date, {
      cycleFilter: "NEXT_DAY",
      assignmentFilter: "unassigned",
    }).map((item) => item.workforce_member_id),
    [],
  );
});


test("search supports display name and external/transporter identifier", () => {
  assert.equal(filterWorkforceDayMembers(members, statuses, date, { search: "alban" }).length, 1);
  assert.equal(filterWorkforceDayMembers(members, statuses, date, { search: "T-002" })[0].display_name, "Sara Blu");
});


test("activity filter is organization data driven", () => {
  assert.deepEqual(filterWorkforceDayMembers(members, statuses, date, { activityFilter: "Consegna DLO2" }).map((item) => item.workforce_member_id), [1]);
});


test("driver counts do not mix with coverage buckets", () => {
  assert.deepEqual(workforceDayCounts(members, statuses, date), {
    total: 3, assigned: 1, unassigned: 2, absent: 0, available: 1,
  });
});


test("batch payload targets many members on exactly one operational day", () => {
  assert.deepEqual(workforceDayBatchPayload({
    date,
    memberIds: new Set([3, 1, 2]),
    choice: "shift:C1",
    activity: "Consegna DLO2",
    notes: "Briefing completato",
    overwritePolicy: "APPLY_TO_EMPTY_ONLY",
  }), {
    operational_date: date,
    workforce_member_ids: [1, 2, 3],
    status_code: "scheduled",
    shift_code: "C1",
    operational_activity: "Consegna DLO2",
    notes: "Briefing completato",
    overwrite_policy: "APPLY_TO_EMPTY_ONLY",
    confirm_overwrite: false,
    confirm_unavailable_override: false,
    source_reference: "manual_day_planning",
  });
});


test("coverage impact is a preview and uses authoritative requirement unchanged", () => {
  const impact = workforceCoverageImpact(coverage(), date, members, statuses, new Set([3]), "shift:C1");
  assert.equal(impact.length, 0, "NOT_SET must never be assigned to an invented bucket");
  const next = workforceCoverageImpact(coverage(), date, members, [], new Set([1]), "shift:C1")[0];
  assert.deepEqual(next, { key: "NEXT_DAY", label: "NEXT DAY", current: 8, added: 1, requirement: 11 });
  assert.deepEqual(workforceCoverageImpact(coverage(), date, members, [], new Set([1]), "shift:SA"), []);
});


test("under-forecast and requirement warnings are explicit", () => {
  assert.match(workforceDayExitWarning(coverage(), date), /Forecast non ancora coperto/);
  const forecastCovered = coverage({ forecast_gap: 0, coverage_status: "FORECAST_COVERED" });
  forecastCovered.items = forecastCovered.items.map((item) => ({
    ...item,
    forecast_gap: 0,
    coverage_status: "FORECAST_COVERED",
  }));
  assert.match(workforceDayExitWarning(forecastCovered, date), /requirement \+10%/);
});


test("week progress distinguishes covered requirement, warning and forecast gap", () => {
  const result = coverage({ forecast_gap: 0, requirement_gap: 0, coverage_status: "REQUIREMENT_COVERED" });
  assert.equal(workforceWeekProgress(result)[0].status, "FORECAST_GAP", "all forecast buckets must be covered before completion");
});


test("frontend calls one atomic batch-members endpoint and one coverage refresh", async () => {
  const [api, page, component] = await Promise.all([
    source("assets/js/api.js"),
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/modules/workforce-day-planner.js"),
  ]);
  assert.match(api, /saveWorkforceDayMemberBatch[\s\S]*day-status\/batch-members/);
  assert.doesNotMatch(component, /for\s*\([^)]*memberIds[^)]*\)[\s\S]{0,160}applyBatch/);
  assert.match(page, /onApplied:[\s\S]*refreshCoverageAfterStatusSave/);
  assert.match(page, /refreshCoverageAfterStatusSave[\s\S]*planningCoverageBoard\?\.refresh\(\)/);
});


test("quick assign values come from the existing Workforce catalog", async () => {
  const component = await source("assets/js/modules/workforce-day-planner.js");
  assert.match(component, /workforceBulkChoices\(data\(\)\.statuses\)/);
  assert.doesNotMatch(component, /\["C1",\s*"SA",\s*"SB"\]/);
});


test("search has a light debounce and preserves input focus", async () => {
  const component = await source("assets/js/modules/workforce-day-planner.js");
  assert.match(component, /setTimeout[\s\S]*120/);
  assert.match(component, /render\(\{ preserveFocus: true \}\)/);
});

test("planner assets are cache-busted after the combined-filter update", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  const loader = await source("assets/js/modules/workspace-loader.js");
  const component = await source("assets/js/modules/workforce-day-planner.js");
  assert.match(page, /workforce-day-planner\.js\?v=2/);
  assert.match(loader, /workforce-day-planner\.css\?v=2/);
  assert.match(component, /workforce-day-planner-state\.js\?v=2/);
  assert.match(component, /workforce-day-planner-presenter\.js\?v=2/);
});


test("mobile planner has controlled scroll, sticky actions and 44px targets", async () => {
  const css = await source("assets/css/workforce-day-planner.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /workforce-day-action-bar[\s\S]*position: sticky/);
  assert.match(css, /min-height: 44px/);
  assert.match(css, /overflow-x: auto/);
});

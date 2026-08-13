import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  operationalCyclePlanningLabel,
  renderWorkforceCalendar,
} from "../assets/js/modules/workforce-calendar-view.js";
import {
  filterWorkforcePlanningMembers,
  workforceActivitySummary,
  workforceOperationalActivities,
  workforceSummary,
} from "../assets/js/modules/workforce-view.js";
import { workforceWeekCopyValueLabel } from "../assets/js/modules/workforce-week-copy.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function calendarContainer() {
  return {
    innerHTML: "",
    querySelectorAll() { return []; },
  };
}


const members = [
  { workforce_member_id: 1, display_name: "Driver A", operational_cycle: "NEXT_DAY" },
  { workforce_member_id: 2, display_name: "Driver B", operational_cycle: "SAME_DAY" },
  { workforce_member_id: 3, display_name: "Driver C", operational_cycle: "NOT_SET" },
];
const statuses = [
  { workforce_member_id: 1, date: "2026-08-10", status_code: "scheduled", shift_code: "C1", operational_activity: "Consegna DLO2" },
  { workforce_member_id: 2, date: "2026-08-10", status_code: "scheduled", shift_code: "SA", operational_activity: "Supporto" },
];


test("planning renders canonical cycle badges and NOT_SET profile action", () => {
  assert.equal(operationalCyclePlanningLabel("NEXT_DAY"), "NEXT DAY");
  assert.equal(operationalCyclePlanningLabel("SAME_DAY"), "SAME DAY");
  assert.equal(operationalCyclePlanningLabel("NOT_SET"), "CICLO NON IMPOSTATO");
  const container = calendarContainer();
  renderWorkforceCalendar(
    container, members, statuses, "week", () => {}, () => {},
    { dateFrom: "2026-08-10", dateTo: "2026-08-16" },
  );
  assert.match(container.innerHTML, />NEXT DAY</);
  assert.match(container.innerHTML, />SAME DAY</);
  assert.match(container.innerHTML, />CICLO NON IMPOSTATO</);
  assert.match(container.innerHTML, /data-workforce-member-edit="3">Completa anagrafica/);
  assert.match(container.innerHTML, /Consegna DLO2/);
});


test("cycle and real-activity filters preserve canonical member scope", () => {
  assert.deepEqual(
    filterWorkforcePlanningMembers(members, statuses, "NEXT_DAY", "all").map((item) => item.workforce_member_id),
    [1],
  );
  assert.deepEqual(
    filterWorkforcePlanningMembers(members, statuses, "SAME_DAY", "all").map((item) => item.workforce_member_id),
    [2],
  );
  assert.deepEqual(
    filterWorkforcePlanningMembers(members, statuses, "NOT_SET", "all").map((item) => item.workforce_member_id),
    [3],
  );
  assert.deepEqual(
    filterWorkforcePlanningMembers(members, statuses, "all", "Consegna DLO2").map((item) => item.workforce_member_id),
    [1],
  );
});


test("activity catalog and summary derive only from persisted planning values", () => {
  assert.deepEqual(workforceOperationalActivities(statuses), ["Consegna DLO2", "Supporto"]);
  assert.deepEqual(workforceOperationalActivities([]), []);
  assert.deepEqual(workforceActivitySummary([
    ...statuses,
    { workforce_member_id: 1, operational_activity: "Consegna DLO2" },
    { workforce_member_id: 3, operational_activity: null },
  ]), { "Consegna DLO2": 2, Supporto: 1 });
});


test("planning summary counts the three canonical cycles", () => {
  const summary = workforceSummary(members, statuses, []);
  assert.equal(summary.members, 3);
  assert.equal(summary.nextDay, 1);
  assert.equal(summary.sameDay, 1);
  assert.equal(summary.cycleNotSet, 1);
});


test("multi-day and single-day editors send operational activity in the existing writes", async () => {
  const [html, page] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(html, /id="workforceMultiDayActivity"/);
  assert.match(html, /id="workforceOperationalActivity"/);
  assert.match(page, /payload\.operational_activity = byId\("workforceMultiDayActivity"\)/);
  assert.match(page, /operational_activity: byId\("workforceOperationalActivity"\)/);
  assert.match(page, /saveWorkforceDayStatusesBatch\(payload\)/);
});


test("week copy exposes preserved activity and no activity is invented", () => {
  assert.match(workforceWeekCopyValueLabel({
    status_code: "scheduled",
    shift_code: "C1",
    operational_activity: "Consegna DLO2",
  }), /Consegna DLO2/);
  assert.doesNotMatch(workforceWeekCopyValueLabel({ status_code: "scheduled", shift_code: "C1" }), /undefined|null/);
});


test("activity filter stays hidden without real data and no compatibility rule is invented", async () => {
  const [html, page] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(html, /id="workforcePlanningActivityFilterLabel" hidden/);
  assert.match(page, /activities\.length === 0/);
  assert.doesNotMatch(page, /COMPATIBILE|DA VERIFICARE|incompatib/i);
});


test("planning cycle and activity controls fit the 390px layout", async () => {
  const css = await source("assets/css/workforce-calendar.css");
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?\.workforce-planning-filters[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /\.workforce-operational-activity[\s\S]*?text-overflow: ellipsis/);
});

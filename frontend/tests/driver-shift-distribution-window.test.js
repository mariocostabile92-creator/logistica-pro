import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  distributionWindowForAnchor,
} from "../assets/js/modules/driver-shift-distribution.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("selected Workforce date becomes its Monday-Sunday window", () => {
  assert.deepEqual(distributionWindowForAnchor("2026-08-12"), {
    period_start: "2026-08-10",
    period_end: "2026-08-16",
  });
  assert.deepEqual(distributionWindowForAnchor("2026-08-16"), {
    period_start: "2026-08-10",
    period_end: "2026-08-16",
  });
});


test("Distribuisci turni opens an explicit accessible week dialog", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /id="driverShiftDistributionWindowDialog"/);
  assert.match(html, /aria-labelledby="driverShiftDistributionWindowTitle"/);
  assert.match(html, /id="driverShiftDistributionWeek" type="date"/);
  assert.match(controller, /elements\.entry\.addEventListener\("click", openWindowDialog\)/);
  assert.match(controller, /windowDialog\.showModal\(\)/);
});


test("default week comes from the active Workforce calendar window", async () => {
  const [workforce, planning] = await Promise.all([
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/modules/driver-shift-planning.js"),
  ]);
  assert.match(workforce, /getDistributionWindow: \(\) => selectedCalendarWindow\(\)/);
  assert.match(planning, /getDefaultWindow: getDistributionWindow/);
  assert.doesNotMatch(workforce, /getDistributionWindow:[^\n]*planning\.period_start/);
});


test("prepare API sends the selected window instead of the annual planning range", async () => {
  const [api, controller] = await Promise.all([
    source("assets/js/api.js"),
    source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(api, /prepareDriverShiftDistribution\(planningId, period = null\)/);
  assert.match(api, /body: period \? JSON\.stringify\(period\)/);
  assert.match(controller, /prepareDistribution\(state\.planning\.id, state\.pendingWindow\)/);
  assert.doesNotMatch(controller, /prepareDistribution\(state\.planning\.id\);/);
});


test("week outside the ACTIVE planning is blocked before submit", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /window\.period_start >= state\.planning\.period_start/);
  assert.match(controller, /window\.period_end <= state\.planning\.period_end/);
  assert.match(controller, /elements\.windowConfirm\.disabled = !valid/);
});


test("missing current distribution remains an empty non-error state", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(
    controller,
    /quietMissing && error\?\.status === 404[\s\S]*state\.model = null;[\s\S]*render\(\);[\s\S]*return;/,
  );
  const setPlanning = controller.slice(controller.indexOf("setPlanning(planning)"));
  assert.doesNotMatch(setPlanning, /load\(\{ quietMissing: true \}\)/);
});


test("visible period is reused by shared portal and group message", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /periodStart: state\.model\.distribution\.period_start/);
  assert.match(controller, /periodEnd: state\.model\.distribution\.period_end/);
  assert.match(controller, /windowLabel\.textContent = `\$\{window\.period_start\} - \$\{window\.period_end\}`/);
});


test("weekly distribution dialog fits 390px without fixed canvas", async () => {
  const css = await source("assets/css/driver-shift-distribution.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /driver-shift-window-dialog[\s\S]*calc\(100vw - 1\.5rem\)/);
  assert.match(css, /driver-shift-window-dialog > div[\s\S]*min-width: 0/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

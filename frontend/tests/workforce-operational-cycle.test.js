import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { operationalCycleLabel } from "../assets/js/modules/workforce-member-create.js";


const source = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");


test("Workforce exposes the new driver action and a complete canonical create form", async () => {
  const html = await source("index.html");
  assert.match(html, /id="workforceNewMemberBtn"[^>]*>\+ Nuovo driver</);
  for (const id of [
    "workforceNewFirstName", "workforceNewLastName", "workforceNewExternalId",
    "workforceNewPhone", "workforceNewEmail", "workforceNewMemberActive",
    "workforceNewEmploymentType",
    "workforceNewOperationalCycle", "workforceNewNotes",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /value="NEXT_DAY">Next Day/);
  assert.match(html, /value="SAME_DAY">Same Day/);
  assert.match(html, /value="NOT_SET">Non impostato/);
});


test("operational cycle labels never leak technical values into the UI", () => {
  assert.equal(operationalCycleLabel("NEXT_DAY"), "Next Day");
  assert.equal(operationalCycleLabel("SAME_DAY"), "Same Day");
  assert.equal(operationalCycleLabel("NOT_SET"), "Non impostato");
  assert.equal(operationalCycleLabel("UNKNOWN"), "Non impostato");
});


test("create success uses the shared organization-scoped Workforce API", async () => {
  const [api, create, page] = await Promise.all([
    source("assets/js/api.js"),
    source("assets/js/modules/workforce-member-create.js"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(api, /createWorkforceMember[\s\S]*api\/plugins\/workforce\/v1\/members/);
  assert.match(create, /await createWorkforceMember/);
  assert.match(create, /employment_type: byId\("workforceNewEmploymentType"\)/);
  assert.match(page, /initWorkforceMemberCreate/);
  assert.match(page, /await refresh\(\)/);
});


test("driver detail edits cycle and status while preserving contract type", async () => {
  const [html, detail, page] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-detail-panel.js"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(html, /id="workforceOperationalCycle"/);
  assert.match(html, /id="workforceMemberActive"/);
  assert.match(html, /id="workforceEmploymentType"/);
  assert.match(detail, /member\.operational_cycle/);
  assert.match(page, /operational_cycle: byId\("workforceOperationalCycle"\)\.value/);
  assert.match(page, /active: byId\("workforceMemberActive"\)\.value === "true"/);
});


test("Workforce list cards show and filter all three cycle states", async () => {
  const [html, card, state, presenter] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/workforce-availability/availability-card.js"),
    source("assets/js/modules/workforce-availability/availability-state.js"),
    source("assets/js/modules/workforce-availability/availability-presenter.js"),
  ]);
  assert.match(html, /id="workforceCycleFilter"/);
  assert.match(card, /workforce-cycle-badge/);
  assert.match(card, /NEXT_DAY: "Next Day"/);
  assert.match(card, /SAME_DAY: "Same Day"/);
  assert.match(state, /filters\.cycle === "all" \|\| driver\.operational_cycle === filters\.cycle/);
  assert.match(presenter, /workforceCycleFilter: "cycle"/);
});


test("import preview shows Next Day, Same Day and unrecognized counts", async () => {
  const view = await source("assets/js/modules/workforce-view.js");
  assert.match(view, /preview\.next_day_detected/);
  assert.match(view, /preview\.same_day_detected/);
  assert.match(view, /preview\.operational_cycle_unrecognized/);
});


test("new driver dialog is responsive at 390 px without a fixed canvas", async () => {
  const css = await source("assets/css/workforce-panel.css");
  assert.match(css, /@media \(max-width: 420px\)[\s\S]*workforce-member-create-dialog/);
  assert.match(css, /grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /min-height: 44px/);
  assert.doesNotMatch(css, /workforce-member-create-dialog[\s\S]{0,500}width:\s*390px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { matchesConsecutivity } from "../assets/js/modules/workforce-consecutivity/consecutivity-state.js";
import { planningDriverOptions } from "../assets/js/modules/workforce-consecutivity/planning-adapter.js";

const source = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");
const driver = (status, effective, planned, override = null) => ({
  consecutivity: {
    calculated_status: status,
    effective_consecutive_days: effective,
    planned_consecutive_days: planned,
    override,
  },
});

test("consecutivity filters distinguish regular attention limit insufficient and overrides", () => {
  assert.equal(matchesConsecutivity(driver("regolare", 2, 2), { consecutivity: "regolare", consecutiveMin: "", consecutiveMax: "", overrideOnly: false }), true);
  assert.equal(matchesConsecutivity(driver("attenzione", 4, 5), { consecutivity: "attenzione", consecutiveMin: "5", consecutiveMax: "5", overrideOnly: false }), true);
  assert.equal(matchesConsecutivity(driver("limite_raggiunto", 6, 6), { consecutivity: "regolare", consecutiveMin: "", consecutiveMax: "", overrideOnly: false }), false);
  assert.equal(matchesConsecutivity(driver("dati_insufficienti", null, null), { consecutivity: "dati_insufficienti", consecutiveMin: "", consecutiveMax: "", overrideOnly: false }), true);
  assert.equal(matchesConsecutivity(driver("limite_raggiunto", 6, 6, { id: "O1" }), { consecutivity: "all", consecutiveMin: "", consecutiveMax: "", overrideOnly: true }), true);
});

test("Planning consumes only the Workforce decision contract", () => {
  const options = planningDriverOptions({ planning: { drivers: [
    { external_identifier: "D1", display_name: "Mario", selectable: true, warning: null },
    { external_identifier: "D2", display_name: "Giulia", selectable: true, warning: "Quinto giorno" },
    { external_identifier: "D3", display_name: "Luca", selectable: false, warning: null },
  ] } });
  assert.match(options, /D1/);
  assert.match(options, /D2 · Attenzione/);
  assert.doesNotMatch(options, /D3/);
});

test("P4.2 architecture keeps calculation policy override presentation and filters separated", async () => {
  const names = [
    "consecutivity-state", "consecutivity-presenter", "consecutivity-kpi",
    "consecutivity-card", "consecutivity-detail", "consecutivity-filters",
    "planning-adapter",
  ];
  const files = await Promise.all(names.map((name) => source(`assets/js/modules/workforce-consecutivity/${name}.js`)));
  assert.ok(files.every((content) => content.length > 100));
  assert.ok(files.slice(0, 6).every((content) => !/fetch\s*\(/.test(content)));
});

test("cards and detail expose effective planned sources policy sequence and override", async () => {
  const [card, detail, html] = await Promise.all([
    source("assets/js/modules/workforce-consecutivity/consecutivity-card.js"),
    source("assets/js/modules/workforce-consecutivity/consecutivity-detail.js"),
    source("index.html"),
  ]);
  for (const field of ["effective_consecutive_days", "planned_consecutive_days", "last_worked_date", "next_planned_work_date"]) assert.match(card, new RegExp(field));
  for (const field of ["sequence", "source_summary", "policy_message", "override"]) assert.match(detail, new RegExp(field));
  for (const label of ["Con limitazioni", "Al limite", "Riposo raccomandato", "Dati insufficienti", "Override attivi"]) assert.match(html, new RegExp(label));
});

test("policy and override use versioned Workforce APIs", async () => {
  const [api, presenter] = await Promise.all([
    source("assets/js/api.js"),
    source("assets/js/modules/workforce-consecutivity/consecutivity-presenter.js"),
  ]);
  assert.match(api, /workforce\/v1\/consecutivity\/policy/);
  assert.match(api, /workforce\/v1\/consecutivity\/overrides/);
  assert.match(presenter, /workforce:consecutivity-changed/);
});

test("Home and responsive CSS expose only the compact consecutivity summary", async () => {
  const [html, mission, css] = await Promise.all([
    source("index.html"), source("assets/js/modules/mission-control/workforce.js"),
    source("assets/css/workforce-foundation.css"),
  ]);
  for (const id of ["operationsHomeWorkforceLimit", "operationsHomeWorkforceRest", "operationsHomeWorkforceInsufficient"]) {
    assert.match(html, new RegExp(id)); assert.match(mission, new RegExp(id));
  }
  assert.match(css, /workforce-consecutivity-strip/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});

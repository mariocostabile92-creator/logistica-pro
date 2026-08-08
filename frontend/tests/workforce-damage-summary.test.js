import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createWorkforceDamageSummary,
  openDamageHistoryInFleet,
  workforceDamageSummaryMarkup,
} from "../assets/js/modules/workforce-damage-summary.js";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

function containerStub() {
  return {
    hidden: true,
    innerHTML: "",
    addEventListener() {},
    replaceChildren() { this.innerHTML = ""; },
  };
}

test("Workforce driver detail contains the compact Danni section", async () => {
  const [html, detail] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/workforce-detail-panel.js"),
  ]);
  assert.match(html, /id="workforceDamageSummary"/);
  assert.match(detail, /createWorkforceDamageSummary/);
  assert.match(detail, /damageSummary\.show\(member\)/);
});

test("summary renders total open and closed counts without case list", () => {
  const markup = workforceDamageSummaryMarkup({
    total_cases: 3,
    open_cases: 1,
    closed_cases: 2,
  });
  assert.match(markup, /Pratiche attribuite[\s\S]*3/);
  assert.match(markup, /Aperte[\s\S]*1/);
  assert.match(markup, /Chiuse[\s\S]*2/);
  assert.doesNotMatch(markup, /case_number|description|attachment|timeline/);
  assert.doesNotMatch(markup, /external_identifier|workforce_member_id|source-/);
});

test("zero damage is a neutral empty state", () => {
  const markup = workforceDamageSummaryMarkup({
    total_cases: 0,
    open_cases: 0,
    closed_cases: 0,
  });
  assert.match(markup, /Nessuna pratica danno attribuita/);
  assert.match(markup, /Apri Fleet → Danni/);
});

test("CTA navigates to Fleet then opens Danni with canonical driverId", () => {
  const events = [];
  const target = new EventTarget();
  target.addEventListener("workspace:navigate", (event) => events.push(event));
  target.addEventListener("damage:open", (event) => events.push(event));

  assert.equal(openDamageHistoryInFleet(42, target), true);
  assert.equal(events[0].type, "workspace:navigate");
  assert.deepEqual(events[0].detail, { view: "fleet" });
  target.dispatchEvent(new CustomEvent("workspace:view-changed", {
    detail: { view: "fleet" },
  }));
  assert.equal(events[1].type, "damage:open");
  assert.deepEqual(events[1].detail, { driverId: 42 });
});

test("changing Workforce driver ignores the previous summary", async () => {
  const container = containerStub();
  let resolveFirst;
  const first = new Promise((resolve) => { resolveFirst = resolve; });
  const loadSummary = (memberId) => memberId === 1
    ? first
    : Promise.resolve({ summary: { total_cases: 2, open_cases: 2, closed_cases: 0 } });
  const presenter = createWorkforceDamageSummary({
    container,
    loadSummary,
    canReadFleet: () => true,
  });

  const pending = presenter.show({ workforce_member_id: 1 });
  await presenter.show({ workforce_member_id: 2 });
  resolveFirst({ summary: { total_cases: 99, open_cases: 99, closed_cases: 0 } });
  await pending;

  assert.match(container.innerHTML, /Pratiche attribuite[\s\S]*2/);
  assert.doesNotMatch(container.innerHTML, />99</);
});

test("damage API failure stays local to the Workforce detail", async () => {
  const container = containerStub();
  const presenter = createWorkforceDamageSummary({
    container,
    loadSummary: async () => { throw new Error("offline"); },
    canReadFleet: () => true,
  });

  await presenter.show({ workforce_member_id: 7 });

  assert.equal(container.hidden, false);
  assert.match(container.innerHTML, /Dati danni non disponibili/);
});

test("Fleet permission gates both summary request and CTA", async () => {
  const container = containerStub();
  let requests = 0;
  const presenter = createWorkforceDamageSummary({
    container,
    loadSummary: async () => { requests += 1; return { summary: {} }; },
    canReadFleet: () => false,
  });

  await presenter.show({ workforce_member_id: 7 });

  assert.equal(requests, 0);
  assert.equal(container.hidden, true);
  assert.doesNotMatch(container.innerHTML, /data-workforce-damage-history/);
});

test("Workforce summary reuses P6.8 API and Fleet driver state", async () => {
  const [summary, damage] = await Promise.all([
    file("assets/js/modules/workforce-damage-summary.js"),
    file("assets/js/modules/damage-workspace.js"),
  ]);
  assert.match(summary, /listDamageCases\(\{ workforce_member_id: memberId \}\)/);
  assert.match(summary, /can\("fleet:read"\)/);
  assert.match(damage, /options\.driverId/);
  assert.match(damage, /filters\.driver = String\(options\.driverId\)/);
});

test("Danni summary remains compact at 390px", async () => {
  const [panel, responsive] = await Promise.all([
    file("assets/css/workforce-panel.css"),
    file("assets/css/workforce-responsive.css"),
  ]);
  assert.match(panel, /\.workforce-damage-summary-metrics[\s\S]*repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(responsive, /@media \(max-width: 390px\)[\s\S]*\.workforce-damage-summary/);
  assert.doesNotMatch(panel, /\.workforce-damage-summary[^}]*width:\s*[4-9]\d{2}px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("P2 architecture separates aggregator renderer sections navigation and state", async () => {
  const names = ["aggregator", "renderer", "sections", "navigation", "state"];
  const sources = await Promise.all(names.map(name =>
    file(`assets/js/modules/fleet-vision/${name}.js`)));
  names.forEach((name, index) => assert.ok(sources[index].length > 80, name));
  assert.doesNotMatch(sources.join("\n"), /fetch\(/);
});

test("filters are local and cover every requested domain", async () => {
  const [sections, state] = await Promise.all([
    file("assets/js/modules/fleet-vision/sections.js"),
    file("assets/js/modules/fleet-vision/state.js"),
  ]);
  for (const label of ["Tutti", "Critiche", "Documenti", "Assicurazioni",
    "Noleggi", "Danni", "Manutenzioni", "Driver Journal", "Disponibilità"]) {
    assert.match(sections, new RegExp(label));
  }
  assert.match(state, /filter === "availability"/);
  assert.match(state, /filter === "alta"/);
});

test("record navigation carries exact identifiers when the source exposes them", async () => {
  const [aggregator, navigation] = await Promise.all([
    file("assets/js/modules/fleet-vision/aggregator.js"),
    file("assets/js/modules/fleet-vision/navigation.js"),
  ]);
  for (const token of ["record_id", "case_number", "maintenance_number",
    "policy_number"]) assert.match(aggregator, new RegExp(token));
  for (const token of ["caseId", "maintenanceId", "policyId"]) {
    assert.match(navigation, new RegExp(token));
  }
  assert.doesNotMatch(navigation, /location\.|history\./);
});

test("P2 does not create decisions, actions or rules", async () => {
  const sources = await Promise.all([
    file("assets/js/modules/fleet-vision-workspace.js"),
    file("assets/js/modules/fleet-vision/aggregator.js"),
    file("assets/js/modules/fleet-vision/renderer.js"),
  ]);
  assert.doesNotMatch(sources.join("\n"), /ACTION_RULES|result\.push\(_decision|risk.?score/i);
});

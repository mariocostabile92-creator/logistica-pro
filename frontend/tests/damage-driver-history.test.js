import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  ALL_DRIVERS,
  UNASSIGNED_DRIVER,
  damageDriverEmptyMessage,
  damageDriverHistoryMarkup,
  damageDriverOptionsMarkup,
  damageDriverQuery,
  normalizeDamageDriverFilter,
} from "../assets/js/modules/damage-driver-history.js";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const members = [
  { workforce_member_id: 11, display_name: "Alessandro Facchetti" },
  { workforce_member_id: 12, display_name: "Giulia Bianchi" },
];

test("Driver filter shows readable Workforce names and canonical member values", () => {
  const markup = damageDriverOptionsMarkup(members, "11");
  assert.match(markup, /Tutti i driver/);
  assert.match(markup, /Driver non attribuito/);
  assert.match(markup, /value="11" selected>Alessandro Facchetti/);
  assert.doesNotMatch(markup, /external_identifier|source-/);
});

test("Driver selection creates only canonical backend filters", () => {
  assert.deepEqual(damageDriverQuery("11"), { workforce_member_id: 11 });
  assert.deepEqual(damageDriverQuery(UNASSIGNED_DRIVER), { driver_unassigned: true });
  assert.deepEqual(damageDriverQuery(ALL_DRIVERS), {});
  assert.equal(normalizeDamageDriverFilter("11", members), "11");
  assert.equal(normalizeDamageDriverFilter("999", members), ALL_DRIVERS);
});

test("Driver history summary is descriptive and contains no technical identifier", () => {
  const markup = damageDriverHistoryMarkup(members[0], {
    total_cases: 3,
    open_cases: 1,
    closed_cases: 2,
  });
  assert.match(markup, /Storico driver/);
  assert.match(markup, /Alessandro Facchetti/);
  assert.match(markup, /Pratiche attribuite[\s\S]*3/);
  assert.match(markup, /Aperte[\s\S]*1/);
  assert.match(markup, /Chiuse[\s\S]*2/);
  assert.doesNotMatch(markup, /workforce_member_id|external_identifier|source-/);
});

test("Driver history uses the required neutral empty states", () => {
  assert.equal(
    damageDriverEmptyMessage("11"),
    "Nessuna pratica danno attribuita a questo driver.",
  );
  assert.equal(
    damageDriverEmptyMessage(UNASSIGNED_DRIVER),
    "Nessuna pratica senza attribuzione driver.",
  );
  assert.equal(damageDriverEmptyMessage(ALL_DRIVERS), null);
});

test("Damage workspace wires Workforce directory, cards, reset and future state entry", async () => {
  const [workspace, history] = await Promise.all([
    file("assets/js/modules/damage-workspace.js"),
    file("assets/js/modules/damage-driver-history.js"),
  ]);
  assert.match(history, /listWorkforceMembers/);
  assert.match(history, /workforce_member_id/);
  assert.match(workspace, /data-damage-filter="driver"/);
  assert.match(workspace, /Driver ·/);
  assert.match(workspace, /Driver non attribuito/);
  assert.match(workspace, /options\.driverId/);
  assert.match(workspace, /driver:\s*ALL_DRIVERS/);
  assert.match(workspace, /await refresh\(\);[\s\S]*renderNavigator\(\)/);
});

test("Driver history layout remains bounded at 390px", async () => {
  const css = await file("assets/css/damage-workspace.css");
  assert.match(css, /\.damage-driver-history/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*\.damage-driver-history/);
  assert.match(css, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
  assert.doesNotMatch(css, /\.damage-driver-history[^}]*width:\s*[5-9]\d{2}px/);
});

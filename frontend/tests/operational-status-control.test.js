import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("manual operational status uses one shared component in all Fleet surfaces", async () => {
  const [component, fleet, vehicleLibrary, damage] = await Promise.all([
    file("assets/js/modules/operational-status-control.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/vehicle-library/index.js"),
    file("assets/js/modules/damage-workspace.js"),
  ]);
  assert.match(component, /export function openOperationalStatusControl/);
  for (const consumer of [fleet, vehicleLibrary, damage]) {
    assert.match(consumer, /openOperationalStatusControl/);
  }
  for (const origin of ["parco_mezzi", "vehicle_library", "damage_case"]) {
    assert.match(`${fleet}\n${vehicleLibrary}\n${damage}`, new RegExp(origin));
  }
});


test("shared control requires reason and supports explicit damage override", async () => {
  const [component, api] = await Promise.all([
    file("assets/js/modules/operational-status-control.js"),
    file("assets/js/api.js"),
  ]);
  assert.match(component, /name="reason"[\s\S]*?required/);
  assert.match(component, /override_restriction/);
  assert.match(component, /pratica aperta/i);
  assert.match(component, /fleet:operational-status-changed/);
  assert.match(component, /planning:availability-changed/);
  assert.doesNotMatch(component, /location\.reload|location\.href|history\.pushState/);
  assert.match(api, /\/api\/fleet\/vehicles\/\$\{vehicleId\}\/operational-status/);
  assert.match(api, /method:\s*"PATCH"/);
});


test("shared control exposes only canonical operational states", async () => {
  const component = await file("assets/js/modules/operational-status-control.js");
  for (const status of [
    "disponibile",
    "disponibile_con_limitazioni",
    "indisponibile",
    "in_manutenzione",
    "in_officina",
  ]) {
    assert.match(component, new RegExp(`"${status}"`));
  }
});

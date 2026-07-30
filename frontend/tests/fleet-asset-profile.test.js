import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("Vehicle Library exposes one editable contractual profile", async () => {
  const [page, view, fleet, api] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/fleet-view.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/api.js"),
  ]);
  assert.match(page, /Profilo contrattuale/);
  assert.match(page, /id="fleetProfileEditor"/);
  assert.match(view, /renderContractProfile\(assetDetail\.profile\)/);
  assert.match(fleet, /saveFleetAssetProfile/);
  assert.match(api, /assets\/\$\{assetId\}\/profile/);
});


test("contract type controls only the applicable economic fields", async () => {
  const fleet = await file("assets/js/modules/fleet-page.js");
  assert.match(fleet, /\["breve_termine", "proprieta"\]\.includes\(type\)/);
  assert.match(fleet, /type !== "breve_termine"/);
  assert.match(fleet, /!\["lungo_termine", "leasing"\]\.includes\(type\)/);
  assert.doesNotMatch(fleet, /location\.reload|history\.pushState/);
});


test("Maintenance and Damage read the shared asset profile", async () => {
  const [maintenance, damage] = await Promise.all([
    file("assets/js/modules/maintenance-workspace.js"),
    file("assets/js/modules/damage-workspace.js"),
  ]);
  assert.match(maintenance, /asset_profile/);
  assert.match(maintenance, /Franchigia prevista/);
  assert.match(maintenance, /Costo fermo mezzo/);
  assert.match(damage, /asset_profile/);
  assert.match(damage, /Profilo contrattuale del mezzo/);
});


test("Fleet provides economic profile counters and responsive editor", async () => {
  const [page, view, css] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/fleet-view.js"),
    file("assets/css/fleet.css"),
  ]);
  for (const id of ["fleetLongTermAssets", "fleetShortTermAssets", "fleetOwnedAssets"]) {
    assert.match(page, new RegExp(id));
    assert.match(view, new RegExp(id));
  }
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.fleet-profile-form-grid[\s\S]*?grid-template-columns: 1fr/);
});

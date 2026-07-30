import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("Fleet exposes Maintenance as an inline workspace node", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/maintenance-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="maintenance"/);
  assert.doesNotMatch(
    page,
    /data-fleet-module="maintenance"[^>]*disabled|Manutenzioni\s*<span class="tag">Prossimamente/,
  );
  assert.match(page, /id="maintenanceWorkspace"/);
  assert.match(fleet, /showMaintenanceWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});


test("Maintenance workspace provides real KPI list and master detail", async () => {
  const module = await file("assets/js/modules/maintenance-workspace.js");
  for (const label of [
    "Manutenzioni aperte",
    "Mezzi in officina",
    "Manutenzioni programmate",
    "Manutenzioni concluse",
    "Gestione interventi del parco mezzi",
  ]) {
    assert.match(module, new RegExp(label));
  }
  assert.match(module, /maintenance-navigator/);
  assert.match(module, /maintenance-list-pane/);
  assert.match(module, /maintenance-detail-pane/);
  assert.match(module, /Torna alla lista/);
});


test("Damage creates a maintenance and Vehicle Library exposes history", async () => {
  const [damage, maintenance, fleet, page] = await Promise.all([
    file("assets/js/modules/damage-workspace.js"),
    file("assets/js/modules/maintenance-workspace.js"),
    file("assets/js/modules/fleet-view.js"),
    file("index.html"),
  ]);
  assert.match(damage, /Crea manutenzione/);
  assert.match(damage, /maintenance:create-from-damage/);
  assert.match(maintenance, /damage_case_id/);
  assert.match(fleet, /fleetDossierMaintenances/);
  assert.match(fleet, /data-maintenance-link/);
  assert.match(page, /<h3>Manutenzioni<\/h3>/);
});


test("Maintenance layout covers desktop tablet and 390 px without fixed canvas", async () => {
  const css = await file("assets/css/maintenance-workspace.css");
  assert.match(css, /grid-template-columns:\s*minmax\(300px,\s*360px\)\s+minmax\(0,\s*1fr\)/);
  assert.match(css, /@media \(max-width:\s*900px\)/);
  assert.match(css, /@media \(max-width:\s*480px\)/);
  assert.match(css, /\.maintenance-mobile-back/);
  assert.doesNotMatch(css, /width:\s*(?:1440|768|390)px/);
});

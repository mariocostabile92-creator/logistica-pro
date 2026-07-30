import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Noleggi is an active inline Fleet workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/rental-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="rentals"/);
  assert.doesNotMatch(page, /data-fleet-module="rentals"[^>]*disabled|Noleggi\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="rentalWorkspace"/);
  assert.match(fleet, /showRentalWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("rental workspace provides workflow KPI master detail and editing", async () => {
  const module = await file("assets/js/modules/rental-workspace.js");
  for (const text of [
    "Gestione dei veicoli sostitutivi", "Nuovo noleggio", "Modifica noleggio",
    "Noleggi attivi", "Noleggi programmati", "Noleggi conclusi",
    "Mezzi sostituiti", "Programmato", "Attivo", "Prorogato",
    "Concluso", "Annullato", "Torna alla lista",
  ]) assert.match(module, new RegExp(text));
  assert.match(module, /createRental/);
  assert.match(module, /updateRental/);
  assert.match(module, /rental-navigator/);
});

test("Damage Maintenance and Vehicle Library expose rentals", async () => {
  const [damage, maintenance, page, fleet, view] = await Promise.all([
    file("assets/js/modules/damage-workspace.js"),
    file("assets/js/modules/maintenance-workspace.js"), file("index.html"),
    file("assets/js/modules/fleet-page.js"), file("assets/js/modules/fleet-view.js"),
  ]);
  assert.match(damage, /Crea noleggio/);
  assert.match(damage, /damage_case_id/);
  assert.match(maintenance, /Crea noleggio/);
  assert.match(maintenance, /maintenance_id/);
  assert.match(page, /fleetDossierRentals/);
  assert.match(fleet, /listRentals/);
  assert.match(view, /replacement_vehicle/);
});

test("rental responsive layout supports desktop tablet and mobile", async () => {
  const css = await file("assets/css/rental-workspace.css");
  assert.match(css, /minmax\(360px,.95fr\) minmax\(0,1.25fr\)/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.rental-mobile-back/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Fleet Vision Engine is an active inline workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/fleet-vision-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="vision"/);
  assert.doesNotMatch(page, /Fleet Vision Engine\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="fleetVisionWorkspace"/);
  assert.match(fleet, /showFleetVisionWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("Fleet Vision has four concise sections and grouped explainable criticalities", async () => {
  const [module, sections, aggregator, navigation] = await Promise.all([
    file("assets/js/modules/fleet-vision-workspace.js"),
    file("assets/js/modules/fleet-vision/sections.js"),
    file("assets/js/modules/fleet-vision/aggregator.js"),
    file("assets/js/modules/fleet-vision/navigation.js"),
  ]);
  for (const text of ["Fleet Snapshot", "Criticità", "Operatività", "Accessi rapidi",
    "Mezzi operativi", "Mezzi indisponibili", "Mezzi in manutenzione",
    "Pratiche danno aperte", "Documenti mancanti", "Contratti in scadenza",
    "Assicurazioni in scadenza", "Driver Journal incompleti", "Perché?",
    "Apri Fleet Brain"]) assert.match(sections, new RegExp(text));
  assert.match(navigation, /Apri record originale/);
  assert.match(sections, /data-fve-vehicle-toggle/);
  assert.match(sections, /slice\(0, 5\)/);
  assert.match(sections, /Mostra tutte/);
  assert.match(module, /loadFleetVisionExcellence/);
  assert.match(aggregator, /getFleetVision/);
  assert.match(aggregator, /listJournalControlRoom/);
  assert.match(aggregator, /listVehicleAttachments/);
  assert.doesNotMatch(module + sections + aggregator, /risk.?score|preditt|machine learning|heatmap/i);
});

test("Vehicle Library opens Fleet Vision filtered by vehicle", async () => {
  const [fleet, renderer] = await Promise.all([
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/vehicle-dossier/renderer.js"),
  ]);
  assert.match(renderer, /Apri Fleet Vision/);
  assert.match(fleet, /showFleetVisionWorkspace\(\{ vehicle_id: vehicleId\(\) \}\)/);
});

test("Fleet Vision responsive layout has no fixed canvas", async () => {
  const css = await file("assets/css/fleet-vision-workspace.css");
  for (const selector of [".fve2-snapshot",
    ".fve2-vehicle-group", ".fve2-operations", ".fve2-quick"]) {
    assert.match(css, new RegExp(selector.replace(".", "\\.")));
  }
  assert.match(css, /@media\(max-width:1000px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

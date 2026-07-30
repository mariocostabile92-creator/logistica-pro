import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Giornale di bordo opens the inline Journal Control Room", async () => {
  const [page, fleet, module, publicJournal] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/journal-control-room.js"),
    file("journal/index.html"),
  ]);
  assert.match(page, /data-fleet-module="journal"/);
  assert.match(page, /id="journalControlRoom"/);
  assert.match(fleet, /showJournalControlRoom/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
  assert.match(publicJournal, /Driver|Journal|Giornale/i);
});

test("Control Room exposes real KPI filters list and inline detail", async () => {
  const module = await file("assets/js/modules/journal-control-room.js");
  for (const text of ["Journal Control Room", "Completate oggi", "Prese in carico",
    "Rientri", "Con anomalie", "Incomplete", "Ultimi 7 giorni", "Ultimi 30 giorni",
    "Apri documento operativo", "Apri dossier mezzo", "Torna alla lista"]) {
    assert.match(module, new RegExp(text));
  }
  assert.match(module, /listJournalControlRoom/);
  assert.match(module, /data-jcr-search/);
  assert.match(module, /data-jcr-detail/);
});

test("Control Room links Vehicle Library operational documents and Damage", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/journal-control-room.js"),
  ]);
  assert.match(page, /fleetDossierOpenControlRoom/);
  assert.match(fleet, /vehicle_id: state\.fleetPlugin\.selectedAssetId/);
  assert.match(module, /fleet:vehicle-open/);
  assert.match(module, /damage:open/);
  assert.match(module, /damage_case_number/);
  assert.match(module, /Anomalia da gestire/);
});

test("Control Room responsive CSS supports desktop tablet and mobile", async () => {
  const css = await file("assets/css/journal-control-room.css");
  assert.match(css, /grid-template-columns:minmax\(300px,.85fr\) minmax\(0,1.4fr\)/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.jcr-back/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

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
    "Apri documento operativo", "Apri dossier mezzo", "Torna alla lista",
    "Genera procedura Driver", "Genera link", "Link Driver", "Copia link",
    "Generata", "Aperta", "In compilazione", "Completata"]) {
    assert.match(module, new RegExp(text));
  }
  assert.match(module, /listJournalControlRoom/);
  assert.match(module, /data-jcr-search/);
  assert.match(module, /data-jcr-detail/);
  assert.match(module, /createJournalDriverSession/);
  assert.match(module, /navigator\.clipboard\.writeText/);
  assert.match(module, /new URL\(result\.link_path, location\.origin\)/);
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
  assert.match(css, /\.jcr-session-datetime/);
  assert.match(css, /\.jcr-session-result/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

test("shared Driver Session preloads immutable assignment and lifecycle", async () => {
  const [page, index, flow, api] = await Promise.all([
    file("journal/index.html"),
    file("assets/js/modules/driver-journal/index.js"),
    file("assets/js/modules/driver-journal/flow.js"),
    file("assets/js/modules/driver-journal/api.js"),
  ]);
  assert.match(page, /id="sessionContext"/);
  assert.match(index, /URLSearchParams\(location\.search\)\.get\("session"\)/);
  assert.match(index, /getSharedSession/);
  assert.match(index, /readOnly = true/);
  assert.match(index, /state\.step = 2/);
  assert.match(flow, /markSessionInProgress/);
  assert.match(api, /sessions\/\$\{encodeURIComponent\(sessionId\)\}/);
  assert.doesNotMatch(index, /localStorage|sessionStorage/);
});

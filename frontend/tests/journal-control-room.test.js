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
  const [module, components, renderer, shared] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-control-room/components.js"),
    file("assets/js/modules/journal-control-room/renderer.js"),
    file("assets/js/modules/journal-shared-access.js"),
  ]);
  const presentation = components + renderer + shared;
  for (const text of ["Journal Control Room", "Completate oggi", "Prese in carico",
    "Rientri", "Anomalie", "In compilazione", "giornata corrente", "Archivio GDB",
    "Apri documento operativo", "Apri dossier mezzo", "Torna alla lista",
    "Generata", "Aperta", "In compilazione", "Completata",
    "link condiviso", "Origine", "Avvisi smart"]) {
    assert.match(presentation + module, new RegExp(text, "i"));
  }
  assert.match(module, /listJournalControlRoom/);
  assert.match(module, /data-jcr-search/);
  assert.match(module, /data-jcr-detail/);
  assert.doesNotMatch(presentation + module, /Ultimi 7 giorni|Ultimi 30 giorni|data-jcr-period/);
  assert.doesNotMatch(module, /Genera procedura Driver|createJournalDriverSession|journalSessionGenerator/);
});

test("Control Room links Vehicle Library operational documents and Damage", async () => {
  const [renderer, fleet, module, components] = await Promise.all([
    file("assets/js/modules/vehicle-dossier/renderer.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-control-room/components.js"),
  ]);
  assert.match(renderer, /Vai al Journal/);
  assert.match(fleet, /showJournalControlRoom\(\{ vehicle_id: vehicleId\(\) \}\)/);
  assert.match(module, /fleet:vehicle-open/);
  assert.match(module, /damage:open/);
  assert.match(components, /damage_case_number/);
  assert.match(components, /Anomalia da gestire/);
});

test("Control Room responsive CSS supports desktop tablet and mobile", async () => {
  const css = await file("assets/css/journal-control-room.css");
  assert.match(css, /grid-template-columns:minmax\(320px,.85fr\) minmax\(0,1.4fr\)/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.jcr-back/);
  assert.match(css, /\.jcr-warnings/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

test("shared link is primary and DJ-003 query sessions remain compatible", async () => {
  const [page, index, access, flow, api] = await Promise.all([
    file("journal/index.html"),
    file("assets/js/modules/driver-journal/index.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
    file("assets/js/modules/driver-journal/flow.js"),
    file("assets/js/modules/driver-journal/api.js"),
  ]);
  assert.match(page, /id="sessionContext"/);
  assert.match(page, /id="startButton"[^>]*>Inizia/);
  assert.match(page, /id="driverName"/);
  assert.match(page, /id="driverSurname"/);
  assert.doesNotMatch(page, /workspace-tabs|Configurazione|Planning/);
  assert.match(access, /URLSearchParams\(location\.search\)\.get\("session"\)/);
  assert.match(access, /getSharedSession/);
  assert.match(access, /createSharedSession/);
  assert.match(access, /readOnly = true/);
  assert.match(access, /state\.step = 4/);
  assert.match(flow, /markSessionInProgress/);
  assert.match(flow, /checkSessionWarnings/);
  assert.match(flow, /createSpontaneousSession/);
  assert.match(api, /sessions\/\$\{encodeURIComponent\(sessionId\)\}/);
  assert.match(api, /sessions\/shared/);
  assert.match(api, /\/warnings/);
  assert.doesNotMatch(index, /localStorage|sessionStorage/);
  assert.match(index, /history\.replaceState\(\{\}, "", "\/app\/journal\/"\)/);
});

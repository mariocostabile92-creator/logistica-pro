import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Scadenziario is an active inline Fleet workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/deadlines-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="deadlines"/);
  assert.match(page, /id="deadlinesWorkspace"/);
  assert.match(fleet, /showDeadlinesWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("deadline workspace aggregates filters searches and opens sources", async () => {
  const module = await file("assets/js/modules/deadlines-workspace.js");
  for (const text of ["Controllo centralizzato", "Scadute", "Oggi", "7 giorni",
    "30 giorni", "Documenti", "Assicurazioni", "Contratti", "Manutenzioni",
    "Apri modulo origine", "Torna alla lista"]) assert.match(module, new RegExp(text));
  assert.match(module, /listFleetDeadlines/);
  assert.match(module, /deadline:open-source/);
  assert.match(module, /plate.*deadline_type.*module_label.*company/s);
});

test("Vehicle Library shows vehicle deadlines", async () => {
  const [fleet, loader, model] = await Promise.all([
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/vehicle-dossier/loader.js"),
    file("assets/js/modules/vehicle-dossier/model.js"),
  ]);
  assert.match(fleet, /loadVehicleDossier/);
  assert.match(loader, /listFleetDeadlines\(\{ vehicle_id: assetId \}\)/);
  assert.match(model, /data\.deadlines/);
});

test("deadline workspace is responsive without fixed canvas", async () => {
  const css = await file("assets/css/deadlines-workspace.css");
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.detail-open/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

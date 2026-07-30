import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("P3 separates state components renderer and orchestration", async () => {
  const names = ["state", "components", "renderer"];
  const sources = await Promise.all(names.map(name =>
    file(`assets/js/modules/journal-control-room/${name}.js`)));
  names.forEach((name, index) => assert.ok(sources[index].length > 80, name));
  assert.doesNotMatch(sources.join("\n"), /fetch\(/);
});

test("closed cards expose every operational field and textual status", async () => {
  const components = await file("assets/js/modules/journal-control-room/components.js");
  for (const text of ["Driver", "Procedura", "Data", "Ora", "Apri dettaglio",
    "Generata", "Aperta", "In compilazione", "Completata",
    "Completata con anomalia"]) assert.match(components, new RegExp(text));
  assert.match(components, /jcr-status/);
  assert.match(components, /aria-pressed/);
});

test("detail has explicit groups warnings and real media actions", async () => {
  const components = await file("assets/js/modules/journal-control-room/components.js");
  for (const text of ["Driver", "Veicolo", "Procedura", "Timeline", "Checklist",
    "Anomalie", "Avvisi smart", "Allegati", "Azioni", "Motivazione",
    "Suggerimento", "Download", "Apri"]) assert.match(components, new RegExp(text));
  assert.match(components, /<img/);
  assert.match(components, /<video/);
  assert.doesNotMatch(components, /placeholder/i);
});

test("visual contract keeps essential controls readable without hover", async () => {
  const [css, shared] = await Promise.all([
    file("assets/css/journal-control-room.css"),
    file("assets/css/journal-shared-access.css"),
  ]);
  for (const selector of [".jcr-kpi", ".jcr-item", ".jcr-status",
    ".jcr-detail-section", ".jcr-warnings", ".jcr-media"]) {
    assert.match(css, new RegExp(selector.replace(".", "\\.")));
  }
  assert.match(css, /color:#1d2624/);
  assert.match(css, /:focus-visible/);
  assert.match(shared, /color:#1d2624/);
  assert.doesNotMatch(css + shared, /opacity:\\s*\\.\\d/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Documenti is an active inline Fleet workspace node", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/documents-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="documents"/);
  assert.doesNotMatch(page, /data-fleet-module="documents"[^>]*disabled|Documenti\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="documentsWorkspace"/);
  assert.match(fleet, /showDocumentsWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("workspace exposes KPIs master detail creation editing and empty states", async () => {
  const module = await file("assets/js/modules/documents-workspace.js");
  for (const label of [
    "Archivio documentale del parco mezzi", "Documenti totali",
    "Documenti scaduti", "In scadenza", "Mezzi senza documentazione",
    "File mancanti", "Nuovo documento", "Modifica metadati",
    "Torna alla lista", "Nessun documento per il mezzo selezionato",
  ]) assert.match(module, new RegExp(label));
  assert.match(module, /documents-navigator/);
  assert.match(module, /createVehicleDocument/);
  assert.match(module, /updateVehicleDocument/);
  assert.match(module, /mountAttachments/);
  assert.doesNotMatch(module, /upload persistente non è disponibile/);
});

test("search and filters are combinable", async () => {
  const module = await file("assets/js/modules/documents-workspace.js");
  for (const token of [
    "documentsSearch", "documentsStatus", "documentsType", "documentsFile",
    "vehicle_id", "document_type", "has_file", "carta_circolazione",
    "contratto_noleggio", "contratto_leasing", "senza_scadenza",
  ]) assert.match(module, new RegExp(token));
});

test("Vehicle Library opens documents filtered by vehicle", async () => {
  const [fleet, renderer] = await Promise.all([
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/vehicle-dossier/renderer.js"),
  ]);
  assert.match(fleet, /documents:open/);
  assert.match(fleet, /vehicleId:\s*vehicleId\(\)/);
  assert.match(renderer, /Apri documento/);
  assert.match(renderer, /Disponibile|Assente/);
});

test("responsive layout covers desktop tablet and mobile", async () => {
  const css = await file("assets/css/documents-workspace.css");
  assert.match(css, /grid-template-columns:\s*minmax\(340px,\s*\.9fr\)\s+minmax\(0,\s*1\.35fr\)/);
  assert.match(css, /@media \(max-width:\s*900px\)/);
  assert.match(css, /@media \(max-width:\s*600px\)/);
  assert.match(css, /\.documents-mobile-back/);
  assert.match(css, /min-width:\s*0/);
  assert.doesNotMatch(css, /width:\s*(?:1440|768|390)px/);
});

test("document controls expose accessible states and keyboard focus", async () => {
  const [page, module, css] = await Promise.all([
    file("index.html"), file("assets/js/modules/documents-workspace.js"),
    file("assets/css/documents-workspace.css"),
  ]);
  assert.match(page, /data-fleet-module="documents" aria-current="false"/);
  assert.match(module, /aria-current=/);
  assert.match(module, /aria-label=/);
  assert.match(css, /:focus-visible/);
});

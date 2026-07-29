import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Danni is an active inline Fleet workspace", async () => {
  const [html, page, module] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/damage-workspace.js"),
  ]);
  const node = html.match(/data-fleet-module="damage"[\s\S]*?<\/button>/)?.[0] || "";
  assert.match(node, /Danni/);
  assert.doesNotMatch(node, /disabled|Prossimamente/);
  assert.match(html, /id="damageWorkspace"/);
  assert.match(page, /showDamageWorkspace/);
  assert.doesNotMatch(module, /location\.|history\.pushState|window\.open/);
});

test("damage workspace exposes real KPIs search combinable filters and inline detail", async () => {
  const module = await file("assets/js/modules/damage-workspace.js");
  for (const label of [
    "Pratiche aperte", "In valutazione", "In riparazione",
    "Veicoli fermi", "Costo stimato aperto",
  ]) assert.match(module, new RegExp(label));
  for (const filter of [
    "open", "in_valutazione", "in_riparazione", "closed",
    "stopped", "severe", "last_7_days", "last_30_days",
  ]) assert.match(module, new RegExp(`\\["${filter}"`));
  assert.match(module, /data-damage-case/);
  assert.match(module, /damage-detail-grid/);
  assert.match(module, /damage-timeline/);
  assert.match(module, /Anomalie da gestire/);
  assert.match(module, /Nuova pratica manuale/);
});

test("damage workflow uses API persistence and accessible controls", async () => {
  const [api, module, css, documents] = await Promise.all([
    file("assets/js/api.js"),
    file("assets/js/modules/damage-workspace.js"),
    file("assets/css/damage-workspace.css"),
    file("assets/js/modules/vehicle-library/operational-documents.js"),
  ]);
  for (const endpoint of [
    "damage-cases", "damage-candidates", "/status", "/notes",
  ]) assert.match(api, new RegExp(endpoint));
  assert.match(module, /aria-label="Indicatori pratiche danno"/);
  assert.match(module, /aria-pressed/);
  assert.match(css, /@media \(max-width: 480px\)/);
  assert.match(css, /overflow-x: auto/);
  assert.match(documents, /Crea pratica danno/);
  assert.match(documents, /Apri pratica/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { sortDamageCases } from "../assets/js/modules/damage-workspace.js";

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
  assert.match(module, /damage-navigator/);
  assert.match(module, /damage-case-navigator/);
  assert.match(module, /damage-detail-pane/);
  assert.match(module, /aria-current/);
  assert.match(module, /Torna alla lista/);
  assert.match(module, /damage-timeline/);
  assert.match(module, /Anomalie da gestire/);
  assert.match(module, /Nuova pratica manuale/);
});

test("case navigator orders stopped vehicles then severity and recency", () => {
  const items = [
    { id: 1, vehicle_operational_status: "disponibile", severity: "critica", occurred_at: "2026-07-30T10:00:00Z" },
    { id: 2, asset_availability: "indisponibile", vehicle_operational_status: "indisponibile", severity: "bassa", occurred_at: "2026-07-28T10:00:00Z" },
    { id: 3, vehicle_operational_status: "disponibile", severity: "alta", occurred_at: "2026-07-30T11:00:00Z" },
    { id: 4, vehicle_operational_status: "disponibile", severity: "alta", occurred_at: "2026-07-30T12:00:00Z" },
  ];
  assert.deepEqual(sortDamageCases(items).map(({ id }) => id), [2, 1, 4, 3]);
});

test("damage status changes refresh Fleet surfaces without reload", async () => {
  const [damage, fleet, dossier] = await Promise.all([
    file("assets/js/modules/damage-workspace.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/fleet-view.js"),
  ]);
  assert.match(damage, /fleet:operational-status-changed/);
  assert.match(damage, /operational_reason/);
  assert.match(damage, /restoration_status/);
  assert.match(fleet, /fleet:operational-status-changed[\s\S]*?refreshFleet/);
  assert.match(dossier, /fleetDossierOperationalOrigin/);
  assert.doesNotMatch(damage, /location\.reload/);
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
  assert.match(css, /grid-template-columns: minmax\(300px, 360px\) minmax\(0, 1fr\)/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /\.damage-case-card\.selected/);
  assert.match(documents, /Crea pratica danno/);
  assert.match(documents, /Apri pratica/);
});

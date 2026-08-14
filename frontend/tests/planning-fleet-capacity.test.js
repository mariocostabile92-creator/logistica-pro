import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  fleetCapacityDate,
  fleetCapacityMessage,
  fleetCapacityTone,
  renderFleetCapacity,
} from "../assets/js/modules/planning-operations/fleet-capacity.js";


const snapshot = (changes = {}) => ({
  operational_date: "2026-08-15",
  requested_station: null,
  station_scope_applied: false,
  total_vehicles: 158,
  available_vehicles: 124,
  unavailable_vehicles: 28,
  maintenance_vehicles: 1,
  blocked_vehicles: 5,
  unknown_vehicles: 0,
  vehicle_need: null,
  margin: null,
  capacity_status: "NEED_NOT_DETERMINABLE",
  route_assignments_available: false,
  assigned_vehicles: null,
  routes_without_vehicle: null,
  ...changes,
});


test("Fleet capacity is visible without definitive routes", () => {
  const html = renderFleetCapacity(snapshot());
  for (const value of ["158", "124", "28", "Manutenzione", "Bloccati / officina"]) {
    assert.match(html, new RegExp(value));
  }
  assert.match(html, /In attesa delle rotte definitive/);
  assert.doesNotMatch(html, /Mezzi non disponibili/);
  assert.doesNotMatch(html, /Mezzi non ancora assegnati/);
});


test("unknown vehicle need never renders a fake zero", () => {
  const html = renderFleetCapacity(snapshot());
  assert.match(html, /Fabbisogno mezzi non ancora determinabile/);
  assert.match(html, /<strong>—<\/strong><span>Fabbisogno mezzi/);
  assert.equal(fleetCapacityTone(snapshot()), "unknown");
});


test("authoritative need presentations support margin and shortage", () => {
  const sufficient = snapshot({ vehicle_need: 120, margin: 4 });
  assert.equal(fleetCapacityMessage(sufficient), "Capacità Fleet sufficiente");
  assert.equal(fleetCapacityTone(sufficient), "sufficient");
  assert.match(renderFleetCapacity(sufficient), /<strong>\+4<\/strong><span>Margine/);

  const shortage = snapshot({ vehicle_need: 130, margin: -6 });
  assert.equal(fleetCapacityMessage(shortage), "Mancano 6 mezzi");
  assert.equal(fleetCapacityTone(shortage), "shortage");
});


test("route assignments remain a separate route-level fact", () => {
  const html = renderFleetCapacity(snapshot({
    route_assignments_available: true,
    assigned_vehicles: 73,
    routes_without_vehicle: 5,
  }));
  assert.match(html, /73 assegnati/);
  assert.match(html, /5 rotte senza mezzo/);
  assert.doesNotMatch(html, /In attesa delle rotte definitive/);
});


test("date, station limitation and Fleet CTA remain explicit", () => {
  const html = renderFleetCapacity(snapshot({ requested_station: "DLO2" }));
  assert.equal(fleetCapacityDate("2026-08-15"), "15 agosto");
  assert.match(html, /Fleet input · 15 agosto/);
  assert.match(html, /intera organizzazione/);
  assert.match(html, /data-open-fleet/);
});


test("Planning handles Fleet navigation and responsive 390px layout", async () => {
  const [index, css] = await Promise.all([
    readFile(new URL("../assets/js/modules/planning-operations/index.js", import.meta.url), "utf8"),
    readFile(new URL("../assets/css/planning-workspace.css", import.meta.url), "utf8"),
  ]);
  assert.match(index, /data-open-fleet/);
  assert.match(index, /detail:\s*\{\s*view:\s*"fleet"\s*\}/);
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*planning-fleet-metrics[\s\S]*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /planning-fleet-capacity > header button[^}]*min-height:\s*44px/);
  assert.doesNotMatch(css, /planning-fleet-capacity[^}]*width:\s*\d{4}px/);
});


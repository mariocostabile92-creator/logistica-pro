import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  fleetCapacityDate,
  fleetCapacityDetail,
  fleetCapacityMessage,
  fleetCapacityTone,
  fleetVehicleNeedMetric,
  renderFleetCapacity,
} from "../assets/js/modules/planning-operations/fleet-capacity.js";
import { renderKpis } from "../assets/js/modules/planning-operations/kpi.js";


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
  vehicle_need_status: "NOT_CONFIGURED",
  effective_requirement_buckets: [],
  missing_requirement_buckets: ["NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C"],
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
  assert.match(html, /Fabbisogno mezzi da configurare/);
  assert.match(html, /<strong>—<\/strong><span>Mezzi necessari/);
  assert.equal(fleetVehicleNeedMetric(snapshot()), "—");
  assert.equal(fleetCapacityTone(snapshot()), "unknown");
});


test("complete surplus is the only definitive sufficient state", () => {
  const sufficient = snapshot({
    vehicle_need: 120,
    vehicle_need_status: "COMPLETE",
    margin: 4,
  });
  assert.equal(fleetCapacityMessage(sufficient), "Capacità Fleet sufficiente");
  assert.equal(fleetCapacityTone(sufficient), "sufficient");
  assert.equal(fleetVehicleNeedMetric(sufficient), "120");
  assert.match(renderFleetCapacity(sufficient), /<strong>\+4<\/strong><span>Margine/);
});


test("complete shortage is definitive and exposes the missing vehicles", () => {
  const shortage = snapshot({
    vehicle_need: 130,
    vehicle_need_status: "COMPLETE",
    margin: -6,
  });
  assert.equal(fleetCapacityMessage(shortage), "Capacità Fleet insufficiente");
  assert.match(fleetCapacityDetail(shortage), /Mancano 6 mezzi/);
  assert.equal(fleetCapacityTone(shortage), "shortage");
});


test("partial Coverage reports a minimum need and the missing bucket", () => {
  const partial = snapshot({
    total_vehicles: 86,
    available_vehicles: 56,
    unavailable_vehicles: 29,
    maintenance_vehicles: 1,
    blocked_vehicles: 0,
    vehicle_need: 42,
    vehicle_need_status: "PARTIAL",
    effective_requirement_buckets: ["SAME_DAY_A", "SAME_DAY_B_C"],
    missing_requirement_buckets: ["NEXT_DAY"],
    margin: 14,
  });
  const html = renderFleetCapacity(partial);
  assert.equal(fleetCapacityTone(partial), "partial");
  assert.equal(
    fleetCapacityMessage(partial),
    "Capacità Fleet sufficiente sul fabbisogno noto",
  );
  assert.equal(fleetVehicleNeedMetric(partial), "Almeno 42");
  assert.match(html, /Fabbisogno parziale/);
  assert.match(html, /<strong>Almeno 42<\/strong><span>Mezzi necessari/);
  assert.match(html, /<strong>\+14<\/strong><span>Margine noto/);
  assert.match(html, /NEXT DAY ancora da configurare/);
  assert.match(html, /\+14 margine sul fabbisogno noto/);
  assert.match(html, /Il fabbisogno finale può aumentare/);
});


test("partial shortage is already insufficient but may still worsen", () => {
  const partial = snapshot({
    available_vehicles: 56,
    vehicle_need: 60,
    vehicle_need_status: "PARTIAL",
    missing_requirement_buckets: ["NEXT_DAY", "SAME_DAY_B_C"],
    margin: -4,
  });
  const html = renderFleetCapacity(partial);
  assert.equal(fleetCapacityMessage(partial), "Capacità Fleet già insufficiente");
  assert.match(html, /Almeno 60/);
  assert.match(html, /Mancano almeno 4 mezzi/);
  assert.match(html, /NEXT DAY, SAME DAY B-C ancora da configurare/);
  assert.match(html, /Il deficit può aumentare/);
});


test("complete production-like Coverage exposes the real shortage", () => {
  const complete = snapshot({
    total_vehicles: 86,
    available_vehicles: 56,
    unavailable_vehicles: 29,
    maintenance_vehicles: 1,
    blocked_vehicles: 0,
    vehicle_need: 119,
    vehicle_need_status: "COMPLETE",
    effective_requirement_buckets: ["NEXT_DAY", "SAME_DAY_A", "SAME_DAY_B_C"],
    missing_requirement_buckets: [],
    margin: -63,
  });
  const html = renderFleetCapacity(complete);
  assert.equal(fleetCapacityMessage(complete), "Capacità Fleet insufficiente");
  assert.equal(fleetCapacityTone(complete), "shortage");
  assert.match(html, /Mancano 63 mezzi/);
  assert.match(html, /requirement operativo \+10% supera/);
  assert.doesNotMatch(html, /Fabbisogno parziale/);
  assert.doesNotMatch(html, /ancora da configurare/);
});


const kpiSummary = {
    routes_forecast: 108,
    requirement: 119,
    drivers_planned: 117,
    routes_definitive: 80,
    vehicles_assigned: 73,
    requirement_gap: 2,
    conflicts: 0,
};


test("top KPIs render a numeric complete need and keep route assignments separate", () => {
  const html = renderKpis(kpiSummary, snapshot({
    vehicle_need: 119,
    vehicle_need_status: "COMPLETE",
    available_vehicles: 56,
  }));
  assert.match(html, /<strong>119<\/strong><span>Mezzi necessari/);
  assert.match(html, /<strong>56<\/strong><span>Mezzi disponibili/);
  assert.match(html, /<strong>73<\/strong><span>Mezzi assegnati/);
});


test("top KPI renders a known partial need instead of an em dash", () => {
  const html = renderKpis(kpiSummary, snapshot({
    vehicle_need: 42,
    vehicle_need_status: "PARTIAL",
    available_vehicles: 56,
  }));
  assert.match(html, /<strong>Almeno 42<\/strong><span>Mezzi necessari/);
  assert.doesNotMatch(html, /<strong>—<\/strong><span>Mezzi necessari/);
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

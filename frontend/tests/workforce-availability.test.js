import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createAvailabilityState,
  reduceAvailabilityState,
  selectAvailabilityDrivers,
} from "../assets/js/modules/workforce-availability/availability-state.js";

const drivers = [
  { workforce_member_id: 1, display_name: "Ada Verde", external_identifier: "D1", role: "driver", station: "DLO1", contract: "FT", callability_status: "callable", callability_reason: "Nessuna limitazione.", callable: true, availability_status: "available", is_reserve: false, capabilities: ["B"] },
  { workforce_member_id: 2, display_name: "Leo Giallo", external_identifier: "D2", role: "driver", station: "DLO2", contract: "PT", callability_status: "limited", callability_reason: "Limitazione manuale.", callable: true, availability_status: "available_limited", is_reserve: false, capabilities: [] },
  { workforce_member_id: 3, display_name: "Mia Rossa", external_identifier: "D3", role: "lead", station: "DLO1", contract: "FT", callability_status: "not_callable", callability_reason: "Ferie.", callable: false, availability_status: "holiday", is_reserve: false, capabilities: [] },
  { workforce_member_id: 4, display_name: "Rio Blu", external_identifier: "D4", role: "driver", station: "DLO1", contract: "FT", callability_status: "callable", callability_reason: "Disponibile come riserva.", callable: true, availability_status: "available", is_reserve: true, capabilities: [] },
];

function readyState() {
  return reduceAvailabilityState(createAvailabilityState(), {
    type: "snapshot", value: { drivers, summary: {} },
  });
}

test("availability state combines search status role station contract and reserve filters", () => {
  let state = readyState();
  state = reduceAvailabilityState(state, { type: "filter", name: "station", value: "DLO1" });
  state = reduceAvailabilityState(state, { type: "filter", name: "contract", value: "FT" });
  assert.deepEqual(selectAvailabilityDrivers(state).map((item) => item.workforce_member_id), [1, 3, 4]);
  state = reduceAvailabilityState(state, { type: "filter", name: "query", value: "ferie" });
  assert.deepEqual(selectAvailabilityDrivers(state).map((item) => item.workforce_member_id), [3]);
});

test("KPI filters select callable limited unavailable and reserve drivers deterministically", () => {
  let state = reduceAvailabilityState(readyState(), { type: "kpi", filters: { callability: "callable_any" } });
  assert.deepEqual(selectAvailabilityDrivers(state).map((item) => item.workforce_member_id), [1, 2, 4]);
  state = reduceAvailabilityState(state, { type: "kpi", filters: { callability: "limited" } });
  assert.deepEqual(selectAvailabilityDrivers(state).map((item) => item.workforce_member_id), [2]);
  state = reduceAvailabilityState(state, { type: "kpi", filters: { reserve: true } });
  assert.deepEqual(selectAvailabilityDrivers(state).map((item) => item.workforce_member_id), [4]);
});

test("availability architecture is split into service presenter state KPI card detail and tests", async () => {
  const names = ["availability-presenter", "availability-state", "availability-kpi", "availability-card", "availability-detail"];
  const files = await Promise.all(names.map((name) => readFile(new URL(`../assets/js/modules/workforce-availability/${name}.js`, import.meta.url), "utf8")));
  assert.ok(files.every((content) => content.length > 100));
  assert.ok(files.every((content) => !/fetch\s*\(/.test(content)));
});

test("cards expose status reason availability capabilities and real detail action", async () => {
  const card = await readFile(new URL("../assets/js/modules/workforce-availability/availability-card.js", import.meta.url), "utf8");
  for (const field of ["callability_label", "callability_reason", "availability_label", "capabilities"]) assert.match(card, new RegExp(field));
  assert.match(card, /data-workforce-driver-detail/);
});

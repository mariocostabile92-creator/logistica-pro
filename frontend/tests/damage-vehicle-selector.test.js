import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createDamageVehicleSelectorController,
  damageVehicleLabel,
  damageVehicleOptionsMarkup,
  normalizeDamageVehicleAssets,
} from "../assets/js/modules/damage-vehicle-selector.js";
import { createDamageDriverSuggestionController } from "../assets/js/modules/damage-driver-suggestion.js";
import { buildManualDamagePayload } from "../assets/js/modules/damage-workspace.js";


const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const fleetResponse = {
  items: [
    { id: 215, plate: "AB123CD", external_identifier: "FLEET-215", category: "Ford Transit" },
    { id: 91, plate: "XY987ZT", external_identifier: "FLEET-91", category: null },
  ],
};


test("manual damage form no longer exposes a numeric vehicle ID field", async () => {
  const workspace = await file("assets/js/modules/damage-workspace.js");

  assert.doesNotMatch(workspace, /ID veicolo<input[^>]+type="number"/);
  assert.match(workspace, /<label class="damage-vehicle-field">Mezzo/);
  assert.match(workspace, /<select name="vehicle_id"[^>]+data-damage-vehicle-select/);
});


test("vehicle selector loads assets through the existing Fleet source", async () => {
  let calls = 0;
  const controller = createDamageVehicleSelectorController({
    loadAssets: async () => { calls += 1; return fleetResponse; },
  });

  await controller.load();
  const [module, api] = await Promise.all([
    file("assets/js/modules/damage-vehicle-selector.js"),
    file("assets/js/api.js"),
  ]);
  assert.equal(calls, 1);
  assert.equal(controller.getState().phase, "ready");
  assert.match(module, /listFleetAssets/);
  assert.match(api, /api\/plugins\/fleet\/v1\/assets/);
});


test("every selector option exposes at least the vehicle plate", () => {
  const assets = normalizeDamageVehicleAssets(fleetResponse);

  assert.equal(damageVehicleLabel(fleetResponse.items[0]), "AB123CD — Ford Transit");
  assert.equal(damageVehicleLabel(fleetResponse.items[1]), "XY987ZT");
  for (const asset of assets) assert.match(asset.label, new RegExp(asset.plate));
});


test("selector option keeps fleet_assets.id as its internal value", () => {
  const assets = normalizeDamageVehicleAssets(fleetResponse);
  const html = damageVehicleOptionsMarkup({ phase: "ready", assets });

  assert.match(html, /option value="215">AB123CD — Ford Transit/);
  assert.match(html, /option value="91">XY987ZT/);
  assert.doesNotMatch(html, /value="AB123CD"/);
});


test("manual damage payload continues to use the canonical numeric asset ID", () => {
  const payload = buildManualDamagePayload({
    vehicle_id: "215",
    occurred_at: "2026-08-08T11:30",
    description: "Urto laterale",
    manual_reason: "Segnalazione Fleet",
    severity: "alta",
  });

  assert.equal(payload.vehicle_id, 215);
  assert.equal("plate" in payload, false);
  assert.equal("model" in payload, false);
  assert.equal("label" in payload, false);
});


test("selected asset and event date trigger the P6.6 suggestion with canonical ID", async () => {
  const calls = [];
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async (vehicleId, operationalDate) => {
      calls.push([vehicleId, operationalDate]);
      return { status: "NOT_FOUND" };
    },
  });

  await controller.update({ vehicleId: "215", occurredAt: "2026-08-08T11:30" });
  assert.deepEqual(calls, [[215, "2026-08-08"]]);
});


test("changing vehicle invalidates the previous suggestion and requests the new asset", async () => {
  const calls = [];
  const phases = [];
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async (vehicleId) => {
      calls.push(vehicleId);
      return { status: "NOT_FOUND" };
    },
    onStateChange: (state) => phases.push(state.phase),
  });

  await controller.update({ vehicleId: "215", occurredAt: "2026-08-08T11:30" });
  await controller.update({ vehicleId: "91", occurredAt: "2026-08-08T11:30" });
  assert.deepEqual(calls, [215, 91]);
  assert.deepEqual(phases, ["loading", "ready", "loading", "ready"]);
});


test("deselecting the vehicle clears vehicle_id and resets the suggestion", async () => {
  const assets = normalizeDamageVehicleAssets(fleetResponse);
  const options = damageVehicleOptionsMarkup({ phase: "ready", assets });
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async () => ({ status: "NOT_FOUND" }),
  });

  await controller.update({ vehicleId: "215", occurredAt: "2026-08-08T11:30" });
  await controller.update({ vehicleId: "", occurredAt: "2026-08-08T11:30" });
  assert.match(options, /^<option value="">Seleziona un mezzo<\/option>/);
  assert.deepEqual(controller.getState(), { phase: "idle", result: null });
});


test("an organization without vehicles receives the explicit empty state", async () => {
  const controller = createDamageVehicleSelectorController({
    loadAssets: async () => ({ items: [] }),
  });

  await controller.load();
  assert.equal(controller.getState().phase, "empty");
  assert.match(damageVehicleOptionsMarkup(controller.getState()), /Nessun mezzo disponibile\./);
});


test("Fleet loading failures produce a stable local error state", async () => {
  const controller = createDamageVehicleSelectorController({
    loadAssets: async () => { throw new Error("Fleet unavailable"); },
  });

  await assert.doesNotReject(controller.load());
  assert.equal(controller.getState().phase, "error");
  assert.match(
    damageVehicleOptionsMarkup(controller.getState()),
    /Impossibile caricare il parco mezzi\./,
  );
});


test("Fleet asset source is organization-scoped and does not accept arbitrary IDs", async () => {
  const [repository, workspace] = await Promise.all([
    readFile(new URL("../../backend/app/plugins/fleet/infrastructure/repository.py", import.meta.url), "utf8"),
    file("assets/js/modules/damage-workspace.js"),
  ]);

  assert.match(repository, /def list_assets\(\)[\s\S]*?current_organization_id\(\)[\s\S]*?WHERE organization_id = \?/);
  assert.doesNotMatch(workspace, /name="vehicle_id"[^>]*type="(?:number|text)"/);
});


test("vehicle selector remains constrained at 390px without horizontal overflow rules", async () => {
  const [css, workspace] = await Promise.all([
    file("assets/css/damage-workspace.css"),
    file("assets/js/modules/damage-workspace.js"),
  ]);

  assert.match(css, /\.damage-vehicle-field select \{ width: 100%; min-width: 0; \}/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*?\.damage-form[\s\S]*?grid-template-columns: 1fr/);
  assert.match(workspace, /damage-vehicle-status/);
});

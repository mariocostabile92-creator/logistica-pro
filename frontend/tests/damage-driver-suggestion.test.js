import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createDamageDriverSuggestionController,
  damageDriverSuggestionMarkup,
  operationalDateFromInput,
} from "../assets/js/modules/damage-driver-suggestion.js";
import {
  buildManualDamagePayload,
  damageDriverAttributionMarkup,
} from "../assets/js/modules/damage-workspace.js";


const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const match = (name, source = "journal", id = 10) => ({
  status: "MATCH",
  conflict: false,
  driver: { workforce_member_id: id, external_identifier: `DRV-${id}`, display_name: name },
  source,
  evidence: [],
  journal_driver: source === "journal" ? { workforce_member_id: id, display_name: name } : null,
  planning_driver: source === "planning" ? { workforce_member_id: id, display_name: name } : null,
});


test("vehicle and event datetime trigger the suggestion API with operational date", async () => {
  const calls = [];
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async (...args) => {
      calls.push(args);
      return match("Mario Rossi");
    },
  });

  await controller.update({ vehicleId: "42", occurredAt: "2026-08-08T18:30" });

  assert.equal(operationalDateFromInput("2026-08-08T18:30"), "2026-08-08");
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(0, 2), [42, "2026-08-08"]);
  assert.ok(calls[0][2].signal instanceof AbortSignal);
});


test("MATCH journal renders associated driver and Journal source", () => {
  const html = damageDriverSuggestionMarkup({ phase: "ready", result: match("Mario Rossi") });

  assert.match(html, /Driver associato/);
  assert.match(html, /Mario Rossi/);
  assert.match(html, /Fonte:[\s\S]*Journal/);
  assert.match(html, /Rilevato dal Giornale di Bordo/);
  assert.doesNotMatch(html, /workforce_member_id|DRV-10/);
});


test("MATCH planning renders suggested driver and Planning source", () => {
  const html = damageDriverSuggestionMarkup({
    phase: "ready",
    result: match("Luca Bianchi", "planning"),
  });

  assert.match(html, /Driver suggerito/);
  assert.match(html, /Luca Bianchi/);
  assert.match(html, /Fonte:[\s\S]*Planning/);
  assert.match(html, /pianificazione della giornata/);
});


test("MATCH Journal and Planning require explicit confirmation", async () => {
  for (const source of ["journal", "planning"]) {
    const controller = createDamageDriverSuggestionController({
      requestSuggestion: async () => match("Mario Rossi", source, 17),
    });
    await controller.update({ vehicleId: 42, occurredAt: "2026-08-08T18:30" });
    assert.match(damageDriverSuggestionMarkup(controller.getState()), /Conferma driver/);

    const confirmed = controller.confirm();

    assert.deepEqual(confirmed, {
      workforce_member_id: 17,
      attribution_source: source,
      display_name: "Mario Rossi",
    });
    assert.deepEqual(controller.getConfirmedAttribution(), {
      workforce_member_id: 17,
      attribution_source: source,
    });
    assert.match(damageDriverSuggestionMarkup(controller.getState()), /Driver confermato/);
  }
});


test("NOT_FOUND and AMBIGUOUS render neutral explanatory states", () => {
  const notFound = damageDriverSuggestionMarkup({
    phase: "ready",
    result: { status: "NOT_FOUND" },
  });
  const ambiguous = damageDriverSuggestionMarkup({
    phase: "ready",
    result: { status: "AMBIGUOUS" },
  });

  assert.match(notFound, /Nessun driver determinato automaticamente/);
  assert.match(ambiguous, /Pi&ugrave; driver compatibili trovati/);
  assert.match(ambiguous, /selezione manuale/);
});


test("CONFLICT renders Journal and Planning drivers without selecting either", () => {
  const html = damageDriverSuggestionMarkup({
    phase: "ready",
    result: {
      status: "CONFLICT",
      conflict: true,
      journal_driver: { display_name: "Mario Rossi" },
      planning_driver: { display_name: "Luca Bianchi" },
    },
  });

  assert.match(html, /Conflitto di attribuzione/);
  assert.match(html, /Journal[\s\S]*Mario Rossi/);
  assert.match(html, /Planning[\s\S]*Luca Bianchi/);
  assert.match(html, /indicano driver differenti/);
});


test("CONFLICT never creates an automatic confirmation", async () => {
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async () => ({
      status: "CONFLICT",
      conflict: true,
      journal_driver: { workforce_member_id: 1, display_name: "Mario Rossi" },
      planning_driver: { workforce_member_id: 2, display_name: "Luca Bianchi" },
    }),
  });
  await controller.update({ vehicleId: 42, occurredAt: "2026-08-08T18:30" });

  assert.equal(controller.confirm(), null);
  assert.equal(controller.getConfirmedAttribution(), null);
});


test("changing vehicle or date resets and requests the new combination", async () => {
  const calls = [];
  const phases = [];
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async (vehicleId, day) => {
      calls.push([vehicleId, day]);
      return match(`Driver ${vehicleId}`);
    },
    onStateChange: (state) => phases.push(state.phase),
  });

  await controller.update({ vehicleId: 1, occurredAt: "2026-08-08T08:00" });
  controller.confirm();
  assert.ok(controller.getConfirmedAttribution());
  await controller.update({ vehicleId: 2, occurredAt: "2026-08-08T08:00" });
  assert.equal(controller.getConfirmedAttribution(), null);
  controller.confirm();
  await controller.update({ vehicleId: 2, occurredAt: "2026-08-09T08:00" });
  assert.equal(controller.getConfirmedAttribution(), null);

  assert.deepEqual(calls, [[1, "2026-08-08"], [2, "2026-08-08"], [2, "2026-08-09"]]);
  assert.deepEqual(phases, [
    "loading", "ready", "ready",
    "loading", "ready", "ready",
    "loading", "ready",
  ]);
});


test("removing vehicle or date hides and clears the previous suggestion", async () => {
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async () => match("Mario Rossi"),
  });
  await controller.update({ vehicleId: 1, occurredAt: "2026-08-08T08:00" });

  await controller.update({ vehicleId: "", occurredAt: "2026-08-08T08:00" });
  assert.deepEqual(controller.getState(), { phase: "idle", result: null });
  await controller.update({ vehicleId: 1, occurredAt: "" });
  assert.deepEqual(controller.getState(), { phase: "idle", result: null });
});


test("API errors stay local to suggestion and do not throw into the form", async () => {
  const controller = createDamageDriverSuggestionController({
    requestSuggestion: async () => { throw new Error("Backend unavailable"); },
  });

  await assert.doesNotReject(
    controller.update({ vehicleId: 1, occurredAt: "2026-08-08T08:00" }),
  );
  assert.equal(controller.getState().phase, "error");
  assert.match(
    damageDriverSuggestionMarkup(controller.getState()),
    /Impossibile recuperare il driver associato/,
  );
});


test("an older response cannot overwrite the latest vehicle and date", async () => {
  const pending = new Map();
  const requestSuggestion = (vehicleId) => new Promise((resolve) => {
    pending.set(vehicleId, resolve);
  });
  const controller = createDamageDriverSuggestionController({ requestSuggestion });

  const first = controller.update({ vehicleId: 1, occurredAt: "2026-08-08T08:00" });
  const second = controller.update({ vehicleId: 2, occurredAt: "2026-08-08T08:00" });
  pending.get(2)(match("Driver recente", "journal", 2));
  await second;
  pending.get(1)(match("Driver vecchio", "journal", 1));
  await first;

  assert.equal(controller.getState().result.driver.display_name, "Driver recente");
  assert.equal(controller.getState().workforceMemberId, 2);
});


test("manual damage payload remains unchanged and excludes suggestion identity", () => {
  const payload = buildManualDamagePayload({
    vehicle_id: "7",
    occurred_at: "2026-08-08T10:30",
    description: "Graffio",
    manual_reason: "Controllo deposito",
    severity: "media",
  });

  assert.deepEqual(payload, {
    vehicle_id: 7,
    occurred_at: "2026-08-08T10:30",
    description: "Graffio",
    manual_reason: "Controllo deposito",
    severity: "media",
    origin: "manual",
    vehicle_operational_status: "disponibile",
  });
  assert.equal("driver_workforce_member_id" in payload, false);
  assert.equal("driver_attribution_source" in payload, false);
});


test("manual payload includes only confirmed canonical driver data", () => {
  const values = {
    vehicle_id: "7",
    occurred_at: "2026-08-08T10:30",
    description: "Graffio",
    manual_reason: "Controllo deposito",
    severity: "media",
  };
  const payload = buildManualDamagePayload(values, {
    workforce_member_id: 33,
    attribution_source: "journal",
    display_name: "Nome solo visuale",
    external_identifier: "DRV-33",
  });

  assert.equal(payload.workforce_member_id, 33);
  assert.equal(payload.attribution_source, "journal");
  assert.equal("display_name" in payload, false);
  assert.equal("external_identifier" in payload, false);
});


test("damage detail presents attribution without technical identifiers", () => {
  const attributed = damageDriverAttributionMarkup({
    workforce_member_id: 33,
    external_identifier_snapshot: "source-technical-id",
    name_snapshot: "Alessandro Facchetti",
    source: "journal",
    attributed_at: "2026-08-08T18:15:00Z",
    attributed_by: "Mario Costabile",
    reason: "Conferma esplicita",
  });
  const empty = damageDriverAttributionMarkup(null);

  assert.match(attributed, /Alessandro Facchetti/);
  assert.match(attributed, /Journal/);
  assert.match(attributed, /Mario Costabile/);
  assert.match(attributed, /Conferma esplicita/);
  assert.doesNotMatch(attributed, /source-technical-id|workforce_member_id|33/);
  assert.match(empty, /Driver non attribuito/);
});


test("API helper, workspace integration and responsive styles are wired", async () => {
  const [api, workspace, css, loader, page, app, html] = await Promise.all([
    file("assets/js/api.js"),
    file("assets/js/modules/damage-workspace.js"),
    file("assets/css/damage-workspace.css"),
    file("assets/js/modules/workspace-loader.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/app.js"),
    file("index.html"),
  ]);

  assert.match(api, /damage-cases\/driver-suggestion/);
  assert.match(api, /getDamageDriverSuggestion[\s\S]*?signal/);
  assert.match(workspace, /mountDamageDriverSuggestion/);
  assert.match(workspace, /data-damage-driver-suggestion/);
  assert.match(css, /\.damage-driver-suggestion[\s\S]*?grid-column: 1 \/ -1/);
  assert.match(css, /\.damage-driver-conflict[\s\S]*?minmax\(0, 1fr\)/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*?\.damage-driver-conflict \{ grid-template-columns: 1fr/);
  assert.match(css, /\.damage-driver-confirm[\s\S]*?margin-top/);
  assert.match(css, /\.damage-driver-attribution[\s\S]*?min-width: 0/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*?\.damage-driver-confirm \{ width: 100%/);
  assert.doesNotMatch(css, /width:\s*(?:1440|390)px/);
  assert.match(loader, /damage-workspace\.css\?v=7/);
  assert.match(page, /damage-workspace\.js\?v=11/);
  assert.match(loader, /fleet-page\.js\?v=28/);
  assert.match(app, /workspace-loader\.js\?v=53/);
  assert.match(html, /app\.js\?v=53/);
});

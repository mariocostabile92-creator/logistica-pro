import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getDspDailySnapshot } from "../assets/js/modules/dsp-workspace/api.js";
import {
  applyDspWorkspaceEvent,
  createDspWorkspaceState,
  deriveDspWorkspaceView,
  localToday,
} from "../assets/js/modules/dsp-workspace/state.js";
import {
  partialMessages,
  rowMarkup,
  signalLabel,
} from "../assets/js/modules/dsp-workspace/presenter.js";


const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const DAY = "2026-08-09";

const rows = [
  {
    assignment_id: 11,
    route: "R-101",
    wave: "W-1",
    driver: { planning_identifier: "DRV-1", workforce_member_id: 91, name: "Mario Rossi" },
    vehicle: { planning_identifier: "AA001AA", fleet_asset_id: 71, plate: "AA001AA", model: "Ford Transit" },
    workforce: { availability_status: "available", convocable: true, reason: "Nessuna limitazione.", contract: "Full time", station: "DLO1", consecutivity_indicator: "regolare" },
    fleet: { availability: "available", operational_status: "available" },
    attention_codes: [],
  },
  {
    assignment_id: 12,
    route: "R-202",
    wave: null,
    driver: { planning_identifier: "DRV-2", workforce_member_id: 92, name: "Anna Verdi" },
    vehicle: { planning_identifier: null, fleet_asset_id: null, plate: null, model: null },
    workforce: { availability_status: "holiday", convocable: false, reason: "Ferie.", contract: null, station: "DLO1", consecutivity_indicator: null },
    fleet: { availability: null, operational_status: null },
    attention_codes: ["DRIVER_WITHOUT_VEHICLE", "DRIVER_NOT_AVAILABLE"],
  },
];

const signals = [
  { code: "DRIVER_WITHOUT_VEHICLE", severity: "critical", assignment_id: 12 },
  { code: "DRIVER_NOT_AVAILABLE", severity: "critical", assignment_id: 12 },
  { code: "VEHICLE_NOT_AVAILABLE", severity: "warning", assignment_id: 13 },
];

function snapshot(overrides = {}) {
  return {
    operation_date: DAY,
    planning: { available: true, planning_id: 4, status: "published" },
    sources: {
      planning: { available: true, status: "available", partial: false },
      workforce: { available: true, status: "available", partial: false },
      fleet: { available: true, status: "available", partial: false },
    },
    rows,
    signals,
    partial: false,
    ...overrides,
  };
}

function readyState(overrides = {}) {
  return applyDspWorkspaceEvent(createDspWorkspaceState({ operationDate: DAY }), {
    type: "load-completed",
    snapshot: snapshot(overrides),
  });
}


test("DSP Workspace is present in primary navigation", async () => {
  const html = await file("index.html");
  const navigation = html.match(/<nav class="workspace-tabs"[\s\S]*?<\/nav>/)?.[0] || "";
  assert.match(navigation, /data-workspace-view="dsp"[\s\S]*?>\s*DSP\s*<\/button>/);
});

test("snapshot client sends the selected operation date", async () => {
  let requestedUrl = "";
  await getDspDailySnapshot(DAY, {
    fetcher: async (url) => {
      requestedUrl = url;
      return { ok: true, json: async () => snapshot() };
    },
  });
  assert.equal(requestedUrl, `/api/dsp-workspace/daily-snapshot?operation_date=${DAY}`);
});

test("Today CTA uses the shared local operation date concept", async () => {
  const source = await file("assets/js/modules/dsp-workspace/index.js");
  assert.equal(localToday(new Date("2026-08-09T12:00:00Z")), "2026-08-09");
  assert.match(source, /dspTodayButton|refs\.today[\s\S]*selectDate\(localToday\(\)/);
});

test("changing date reloads the snapshot", async () => {
  const source = await file("assets/js/modules/dsp-workspace/index.js");
  assert.match(source, /refs\.date\.addEventListener\("change"[\s\S]*selectDate\(refs\.date\.value, \{ force: true \}\)/);
});

test("summary counts planned drivers from DSP rows", () => {
  assert.equal(deriveDspWorkspaceView(readyState()).summary.drivers, 2);
});

test("summary counts assigned Fleet vehicles", () => {
  assert.equal(deriveDspWorkspaceView(readyState()).summary.vehicles, 1);
});

test("summary counts backend attention signals", () => {
  assert.equal(deriveDspWorkspaceView(readyState()).summary.attention, 3);
});

test("operational row renders the readable driver", () => {
  const view = deriveDspWorkspaceView(readyState());
  assert.match(rowMarkup(view.rows[0]), /Mario Rossi/);
});

test("operational row renders plate and model", () => {
  const view = deriveDspWorkspaceView(readyState());
  assert.match(rowMarkup(view.rows[0]), /AA001AA[\s\S]*Ford Transit/);
});

test("operational row renders route and wave", () => {
  const view = deriveDspWorkspaceView(readyState());
  assert.match(rowMarkup(view.rows[0]), /R-101[\s\S]*W-1/);
});

test("DRIVER_WITHOUT_VEHICLE has the approved label", () => {
  assert.equal(signalLabel("DRIVER_WITHOUT_VEHICLE"), "Mezzo non assegnato");
});

test("DRIVER_NOT_AVAILABLE has the approved label", () => {
  assert.equal(signalLabel("DRIVER_NOT_AVAILABLE"), "Driver non disponibile");
});

test("VEHICLE_NOT_AVAILABLE has the approved label", () => {
  assert.equal(signalLabel("VEHICLE_NOT_AVAILABLE"), "Mezzo non disponibile");
});

test("attention filter keeps only rows with backend signals", () => {
  const state = applyDspWorkspaceEvent(readyState(), { type: "filter-changed", filter: "attention" });
  assert.deepEqual(deriveDspWorkspaceView(state).rows.map((row) => row.assignment_id), [12]);
});

test("clear filter keeps only rows without backend signals", () => {
  const state = applyDspWorkspaceEvent(readyState(), { type: "filter-changed", filter: "clear" });
  assert.deepEqual(deriveDspWorkspaceView(state).rows.map((row) => row.assignment_id), [11]);
});

test("search finds a driver", () => {
  const state = applyDspWorkspaceEvent(readyState(), { type: "search-changed", search: "Anna" });
  assert.deepEqual(deriveDspWorkspaceView(state).rows.map((row) => row.assignment_id), [12]);
});

test("search finds a plate", () => {
  const state = applyDspWorkspaceEvent(readyState(), { type: "search-changed", search: "AA001" });
  assert.deepEqual(deriveDspWorkspaceView(state).rows.map((row) => row.assignment_id), [11]);
});

test("search finds a route", () => {
  const state = applyDspWorkspaceEvent(readyState(), { type: "search-changed", search: "R-202" });
  assert.deepEqual(deriveDspWorkspaceView(state).rows.map((row) => row.assignment_id), [12]);
});

test("missing authoritative Planning exposes the dedicated empty state", async () => {
  const presenter = await file("assets/js/modules/dsp-workspace/presenter.js");
  const view = deriveDspWorkspaceView(readyState({
    planning: { available: false }, rows: [], signals: [],
  }));
  assert.equal(view.planningAvailable, false);
  assert.match(presenter, /Nessun Planning pubblicato o confermato per questa giornata\./);
});

test("partial source warning is non-blocking", () => {
  const messages = partialMessages({
    workforce: { available: true, partial: true },
    fleet: { available: true, partial: false },
  });
  assert.deepEqual(messages, ["Dati Workforce parzialmente disponibili."]);
  assert.equal(deriveDspWorkspaceView(readyState()).phase, "ready");
});

test("snapshot error exposes retry without breaking navigation", async () => {
  const source = await file("assets/js/modules/dsp-workspace/presenter.js");
  const state = applyDspWorkspaceEvent(createDspWorkspaceState({ operationDate: DAY }), {
    type: "load-failed", error: new Error("down"),
  });
  assert.equal(deriveDspWorkspaceView(state).message, "Impossibile caricare il DSP Workspace.");
  assert.match(source, /actionLabel: "Riprova"[\s\S]*action: "dsp-retry"/);
});

test("rendered row never exposes canonical technical IDs", () => {
  const markup = rowMarkup(deriveDspWorkspaceView(readyState()).rows[0]);
  for (const forbidden of ["assignment_id", "workforce_member_id", "fleet_asset_id", "91", "71"]) {
    assert.doesNotMatch(markup, new RegExp(forbidden));
  }
});

test("390 px layout becomes cards without fixed canvas", async () => {
  const css = await file("assets/css/dsp-workspace.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.dsp-board-row[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /min-width: 0/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});

test("DSP frontend calls only the DSP.2 snapshot endpoint", async () => {
  const [client, index] = await Promise.all([
    file("assets/js/api.js"),
    file("assets/js/modules/dsp-workspace/index.js"),
  ]);
  const dspClient = client.slice(
    client.indexOf("export async function getDspDailySnapshot"),
    client.indexOf("export async function getWorkspaceStatus"),
  );
  assert.match(dspClient, /\/api\/dsp-workspace\/daily-snapshot/);
  assert.doesNotMatch(dspClient + index, /\/api\/(?:planning|plugins\/workforce|plugins\/fleet)/);
});


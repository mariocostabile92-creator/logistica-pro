import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  deleteTransporterMapping,
  getTransporterMappingHistory,
  getTransporterReconciliation,
  putTransporterMapping,
  searchQualityWorkforceCandidates,
} from "../assets/js/modules/dsp-quality/api.js";
import {
  filterReconciliationRows,
  reconciliationMarkup,
} from "../assets/js/modules/dsp-quality/reconciliation-presenter.js";
import {
  applyReconciliationEvent,
  createReconciliationState,
} from "../assets/js/modules/dsp-quality/reconciliation-state.js";
import { qualityDriversMarkup } from "../assets/js/modules/dsp-quality/drivers-presenter.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


const rows = [
  {
    transporter_external_id: "A123",
    mapping_status: "UNMAPPED",
    workforce_member_id: null,
    workforce_display_name: null,
    delivered: "135",
    updated_at: null,
  },
  {
    transporter_external_id: "A456",
    mapping_status: "MATCHED",
    workforce_member_id: 42,
    workforce_display_name: "Mario Rossi",
    delivered: "210",
    updated_at: "2026-08-09T10:00:00Z",
  },
  {
    transporter_external_id: "A789",
    mapping_status: "AMBIGUOUS",
    workforce_member_id: null,
    workforce_display_name: null,
    delivered: null,
    updated_at: "2026-08-09T11:00:00Z",
  },
];


const data = {
  available: true,
  week: 45,
  year: 2025,
  summary: { total: 146, matched: 0, unmapped: 146, ambiguous: 0 },
  rows,
};


function state(overrides = {}) {
  return {
    ...createReconciliationState(),
    open: true,
    phase: "available",
    data,
    ...overrides,
  };
}


test("Driver tab exposes Gestisci associazioni without a new main navigation entry", async () => {
  const html = qualityDriversMarkup({
    phase: "available",
    data: {
      available: true,
      drivers_available: false,
      current_period: { week: 45, year: 2025 },
      summary: data.summary,
      rows: [],
    },
    canManageMappings: true,
    reconciliation: createReconciliationState(),
  });
  const index = await source("index.html");
  assert.match(html, /Gestisci associazioni/);
  assert.doesNotMatch(index, />Associazioni Transporter</);
});


test("reconciliation defaults to Da associare when unmapped rows exist", () => {
  const initial = createReconciliationState();
  const completed = applyReconciliationEvent(initial, {
    type: "reconciliation-completed",
    data,
  });
  assert.equal(completed.filter, "unmapped");
});


test("real 146 unmapped summary is rendered without hardcoding row count", () => {
  const html = reconciliationMarkup(state());
  assert.match(html, /Totali[\s\S]*146/);
  assert.match(html, /Da associare[\s\S]*146/);
});


test("search supports exact Transporter ID and mapped Workforce name", () => {
  assert.deepEqual(filterReconciliationRows(rows, "all", "A123"), [rows[0]]);
  assert.deepEqual(filterReconciliationRows(rows, "all", "mario"), [rows[1]]);
});


test("mapped unmapped and ambiguous filters are explicit", () => {
  assert.deepEqual(filterReconciliationRows(rows, "matched").map(row => row.transporter_external_id), ["A456"]);
  assert.deepEqual(filterReconciliationRows(rows, "unmapped").map(row => row.transporter_external_id), ["A123"]);
  assert.deepEqual(filterReconciliationRows(rows, "ambiguous").map(row => row.transporter_external_id), ["A789"]);
});


test("association panel has dialog semantics and explicit Workforce search", () => {
  const html = reconciliationMarkup(state({ activeExternalId: "A123" }));
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /Cerca driver Workforce/);
  assert.match(html, /data-quality-candidate-search/);
});


test("candidate click only selects and never auto-saves", () => {
  const candidate = {
    workforce_member_id: 7,
    display_name: "Giulia Bianchi",
    station: "DLO2",
    contract: "full_time",
    active: true,
  };
  const selected = applyReconciliationEvent(state(), {
    type: "candidate-selected",
    candidate,
  });
  const html = reconciliationMarkup({ ...selected, activeExternalId: "A123" });
  assert.equal(selected.selectedCandidate, candidate);
  assert.match(html, /A123[\s\S]*Giulia Bianchi/);
  assert.match(html, /Conferma associazione/);
});


test("no candidates has a clear empty state", () => {
  const html = reconciliationMarkup(state({
    activeExternalId: "A123",
    candidatePhase: "available",
    candidates: [],
  }));
  assert.match(html, /Nessun driver Workforce trovato/);
});


test("matched row offers modify remove history and canonical Workforce identity", () => {
  const html = reconciliationMarkup(state({
    activeExternalId: "A456",
    history: [{
      action: "mapping_created",
      actor: "admin",
      created_at: "2026-08-09T10:00:00Z",
      previous_workforce_display_name: null,
      new_workforce_display_name: "Mario Rossi",
    }],
  }));
  assert.match(html, /Modifica associazione/);
  assert.match(html, /Rimuovi associazione/);
  assert.match(html, /Cronologia associazione/);
  assert.match(html, /Mario Rossi/);
});


test("conflict is a visible non-destructive state", () => {
  const conflict = applyReconciliationEvent(state(), {
    type: "mapping-conflict",
    message: "Associazione aggiornata da un altro utente.",
  });
  const html = reconciliationMarkup({ ...conflict, activeExternalId: "A123" });
  assert.equal(conflict.mutationPhase, "conflict");
  assert.match(html, /role="alert"[\s\S]*altro utente/);
});


test("reconciliation endpoint is a read-only GET", async () => {
  let request;
  await getTransporterReconciliation({ fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => data };
  } });
  assert.equal(request.url, "/api/dsp-quality/transporter-mappings/reconciliation");
  assert.equal(request.options.method, "GET");
});


test("Workforce candidate search is server-side and query-scoped", async () => {
  let request;
  await searchQualityWorkforceCandidates("Mario Rossi", { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ items: [] }) };
  } });
  assert.match(request.url, /workforce-candidates\?q=Mario\+Rossi/);
  assert.equal(request.options.method, "GET");
});


test("mapping create sends canonical member ID and optimistic timestamp", async () => {
  let request;
  await putTransporterMapping("A123", {
    workforce_member_id: 42,
    expected_updated_at: null,
  }, { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({}) };
  } });
  assert.equal(request.options.method, "PUT");
  assert.deepEqual(JSON.parse(request.options.body), {
    workforce_member_id: 42,
    expected_updated_at: null,
  });
});


test("remove mapping requires the current optimistic timestamp", async () => {
  let request;
  await deleteTransporterMapping("A456", "2026-08-09T10:00:00Z", {
    fetcher: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({}) };
    },
  });
  assert.equal(request.options.method, "DELETE");
  assert.deepEqual(JSON.parse(request.options.body), {
    expected_updated_at: "2026-08-09T10:00:00Z",
  });
});


test("history endpoint is organization-derived server-side", async () => {
  let request;
  await getTransporterMappingHistory("A123", { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ items: [] }) };
  } });
  assert.equal(request.url, "/api/dsp-quality/transporter-mappings/A123/history");
  assert.equal(request.options.method, "GET");
});


test("controller implements debounce next-unmapped reload and Q7 refresh", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /setTimeout\(\(\) => void loadCandidates\(query\), 250\)/);
  assert.match(controller, /nextUnmapped/);
  assert.match(controller, /loadDrivers\(\{ force: true \}\)/);
  assert.match(controller, /loadReconciliation\(\{ keepFilter: true, advanceAfter:/);
});


test("keyboard workflow supports Escape ArrowDown and Enter", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  for (const key of ["Escape", "ArrowDown", "Enter"]) {
    assert.match(controller, new RegExp(`event\\.key === "${key}"`));
  }
});


test("frontend has no fuzzy or automatic bulk mapping action", async () => {
  const [controller, presenter] = await Promise.all([
    source("assets/js/modules/dsp-quality/index.js"),
    source("assets/js/modules/dsp-quality/reconciliation-presenter.js"),
  ]);
  assert.doesNotMatch(`${controller}\n${presenter}`, /auto.?match|fuzzy|associa automaticamente/i);
  assert.match(presenter, /Nessuna associazione viene salvata automaticamente/);
});


test("responsive layouts cover tablet and 390 mobile without fixed product widths", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 820px\)[\s\S]*dsp-quality-reconciliation-list article/);
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-association-panel[\s\S]*width: 100%/);
  assert.match(css, /dsp-quality-drivers \{[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /dsp-quality-driver-table :is\(tbody, tr, th, td\) \{ min-width: 0; max-width: 100%; \}/);
  assert.match(css, /min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});


test("Q5 overview Q6 metrics and Q7 performance remain wired", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.match(presenter, /persistedOverview\(view\.latest\)/);
  assert.match(presenter, /qualityMetricsMarkup\(view\.metrics\)/);
  assert.match(presenter, /qualityDriversMarkup\(view\.drivers\)/);
});

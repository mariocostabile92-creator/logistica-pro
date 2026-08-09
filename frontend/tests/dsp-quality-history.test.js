import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  getQualityDrivers,
  getQualityMetrics,
  getQualityScorecard,
  getQualityScorecardHistory,
  getTransporterReconciliation,
} from "../assets/js/modules/dsp-quality/api.js";
import { qualityAvailableMarkup } from "../assets/js/modules/dsp-quality/presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const ok = payload => ({ ok: true, json: async () => payload });


function historyItem(overrides = {}) {
  return {
    scorecard_id: "score-47",
    active_revision_id: "revision-2",
    dsp_identifier: "DSP-A",
    station: "DLO2",
    reported_week: 47,
    reported_year: 2026,
    imported_at: "2026-08-09T10:00:00Z",
    source_filename: "scorecard-47.pdf",
    revision_count: 2,
    ...overrides,
  };
}


function scorecard(overrides = {}) {
  return {
    available: true,
    scorecard: {
      id: "score-47",
      revision_id: "revision-2",
      dsp_identifier: "DSP-A",
      station: "DLO2",
      reported_week: 47,
      reported_year: 2026,
      source_provider: "amazon",
    },
    revision: {
      imported_at: "2026-08-09T10:00:00Z",
      source_filename: "scorecard-47.pdf",
      overall_score: "95.1",
      overall_standing: "Fantastic",
      active_number: 2,
      revision_count: 2,
    },
    sections: [],
    focus_areas: [],
    counts: {},
    ...overrides,
  };
}


test("history and selected scorecard clients use canonical read-only endpoints", async () => {
  const requests = [];
  const fetcher = async (url, options) => {
    requests.push([url, options.method]);
    return ok({ items: [] });
  };
  await getQualityScorecardHistory({ fetcher });
  await getQualityScorecard("score/id", { fetcher });
  await getQualityMetrics("score/id", { fetcher });
  await getQualityDrivers("score/id", { fetcher });
  assert.deepEqual(requests, [
    ["/api/dsp-quality/scorecards", "GET"],
    ["/api/dsp-quality/scorecards/score%2Fid", "GET"],
    ["/api/dsp-quality/scorecards/score%2Fid/metrics", "GET"],
    ["/api/dsp-quality/scorecards/score%2Fid/drivers", "GET"],
  ]);
});


test("reconciliation can be read in the selected historical scorecard context", async () => {
  let requestUrl = "";
  await getTransporterReconciliation({
    scorecardId: "score-45",
    fetcher: async url => {
      requestUrl = url;
      return ok({ rows: [] });
    },
  });
  assert.equal(requestUrl, "/api/dsp-quality/transporter-mappings/reconciliation?scorecard_id=score-45");
});


test("history state keeps a canonical selectedScorecardId", () => {
  const state = applyDspQualityEvent(createDspQualityState(), {
    type: "scorecard-history-completed",
    items: [historyItem(), historyItem({ scorecard_id: "score-45", reported_week: 45 })],
    selectedScorecardId: "score-45",
  });
  assert.equal(state.selectedScorecardId, "score-45");
  assert.equal(state.history.items.length, 2);
});


test("changing week invalidates selected detail, metrics, drivers and reconciliation", () => {
  const base = {
    ...createDspQualityState(),
    phase: "available",
    latest: scorecard(),
    history: { phase: "available", items: [historyItem()], error: null },
    metrics: { phase: "available", data: { available: true } },
    drivers: { ...createDspQualityState().drivers, phase: "available", data: { available: true } },
  };
  const next = applyDspQualityEvent(base, {
    type: "scorecard-selection-changed",
    scorecardId: "score-45",
  });
  assert.equal(next.phase, "available");
  assert.equal(next.selectedScorecardId, "score-45");
  assert.equal(next.latest, null);
  assert.equal(next.metrics.phase, "idle");
  assert.equal(next.drivers.phase, "idle");
  assert.equal(next.drivers.reconciliation.phase, "idle");
});


test("selector is persistent above tabs and shows period plus DSP context when needed", () => {
  const view = deriveDspQualityView({
    ...createDspQualityState({ canImport: true }),
    phase: "available",
    latest: scorecard(),
    selectedScorecardId: "score-47",
    history: {
      phase: "available",
      error: null,
      items: [
        historyItem(),
        historyItem({ scorecard_id: "score-45", reported_week: 45 }),
        historyItem({ scorecard_id: "score-b", dsp_identifier: "DSP-B", station: "DLO3" }),
      ],
    },
  });
  const markup = qualityAvailableMarkup(view);
  assert.ok(markup.indexOf("data-quality-scorecard-select") < markup.indexOf("dsp-quality-section-tabs"));
  assert.match(markup, /Week 47 · 2026/);
  assert.match(markup, /DSP-B · DLO3/);
  assert.match(markup, /value="score-47" selected/);
});


test("active revision is explicit and a repeated revision remains one selector option", () => {
  const view = {
    ...createDspQualityState(),
    phase: "available",
    latest: scorecard(),
    selectedScorecardId: "score-47",
    history: { phase: "available", error: null, items: [historyItem()] },
  };
  const markup = qualityAvailableMarkup(view);
  assert.match(markup, /Revisione attiva[\s\S]*2 di 2/);
  assert.equal((markup.match(/<option /g) || []).length, 1);
});


test("selected week loading preserves the selector and never renders stale detail", () => {
  const markup = qualityAvailableMarkup({
    ...createDspQualityState(),
    phase: "available",
    latest: null,
    selectedScorecardId: "score-45",
    history: { phase: "available", error: null, items: [historyItem({ scorecard_id: "score-45", reported_week: 45 })] },
  });
  assert.match(markup, /data-quality-scorecard-select/);
  assert.match(markup, /Caricamento settimana selezionata/);
  assert.doesNotMatch(markup, /Overall Standing/);
});


test("controller keeps lazy tabs, race guards, imported selection and Q8 context", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /scorecardId === state\.selectedScorecardId/);
  assert.match(controller, /if \(state\.section === "metrics"\) void loadMetrics\(\)/);
  assert.match(controller, /if \(state\.section === "drivers"\) void loadDrivers\(\)/);
  assert.match(controller, /preferredScorecardId: result\.scorecard_id/);
  assert.match(controller, /getTransporterReconciliation\(\{[\s\S]*scorecardId: state\.selectedScorecardId/);
  assert.match(controller, /putTransporterMapping\([\s\S]*scorecardId: state\.selectedScorecardId/);
  assert.match(controller, /error\?\.status === 404[\s\S]*excludedScorecardId: scorecardId/);
  assert.ok(controller.indexOf("} catch (error)") < controller.indexOf("if (error?.status === 404"));
  assert.match(controller, /data-quality-scorecard-select[\s\S]*\.focus\(\)/);
});


test("empty history has no selector and history failures use the approved retry", async () => {
  const emptyState = applyDspQualityEvent(createDspQualityState({ canImport: true }), {
    type: "scorecard-history-completed",
    items: [],
    selectedScorecardId: null,
  });
  assert.equal(emptyState.phase, "empty");
  assert.equal(emptyState.selectedScorecardId, null);
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /Impossibile caricare lo storico Quality\./);
  assert.match(controller, /data-quality-retry[\s\S]*loadHistory/);
});


test("tab switching preserves the selected scorecard ID", () => {
  const initial = {
    ...createDspQualityState(),
    selectedScorecardId: "score-45",
  };
  const metrics = applyDspQualityEvent(initial, { type: "section-changed", section: "metrics" });
  const drivers = applyDspQualityEvent(metrics, { type: "section-changed", section: "drivers" });
  assert.equal(drivers.selectedScorecardId, "score-45");
});


test("history selector remains responsive without fixed-width overflow", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /dsp-quality-history-selector[\s\S]*grid-template-columns: auto minmax\(240px, 1fr\)/);
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-history-selector[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /dsp-quality-history-selector select[\s\S]*min-height: 44px/);
});

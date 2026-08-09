import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getLatestQualityScorecard } from "../assets/js/modules/dsp-quality/api.js";
import {
  qualityAvailableMarkup,
  qualityEmptyMarkup,
  qualityLatestErrorMarkup,
  qualityLoadingMarkup,
} from "../assets/js/modules/dsp-quality/presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function latest(overrides = {}) {
  return {
    available: true,
    scorecard: {
      id: "scorecard-id",
      revision_id: "revision-id",
      dsp_identifier: "DSP-READ",
      station: "ST-READ",
      reported_week: 47,
      reported_year: 2025,
      geography: "IT",
      source_provider: "amazon",
    },
    revision: {
      imported_at: "2026-08-09T10:30:00+00:00",
      imported_by: "admin-id",
      source_filename: "weekly-scorecard.pdf",
      detected_template_version: "3.0",
      rank: 4,
      rank_wow_declared: -1,
      overall_score: "45.41",
      overall_standing: "Poor",
    },
    sections: [
      { section_key: "compliance_safety", label: "Compliance and Safety", standing: "Fantastic" },
      { section_key: "delivery_quality_swc", label: "Delivery Quality & SWC", standing: "Poor" },
      { section_key: "capacity", label: "Capacity", standing: "Fantastic" },
    ],
    focus_areas: [
      { position: 1, metric_key: "delivery_success_conditions_dpmo", source_label: "Delivery Success Conditions" },
      { position: 2, metric_key: "delivery_completion_rate", source_label: "Delivery Completion Rate" },
      { position: 3, metric_key: null, source_label: "CDF DPMO" },
    ],
    counts: {
      dsp_metrics: 18,
      transporter_rows: 159,
      working_hour_exceptions: 0,
      mapped_transporters: 8,
      unmapped_transporters: 150,
      ambiguous_transporters: 1,
    },
    standard_set: { available: true, id: "standard-id", provider: "amazon", version: "3.0" },
    ...overrides,
  };
}


function availableView(overrides = {}) {
  return deriveDspQualityView({
    ...createDspQualityState({ canImport: true }),
    phase: "available",
    latest: latest(),
    ...overrides,
  });
}


test("Quality client loads the persisted latest endpoint with GET", async () => {
  let request;
  const payload = latest();
  const result = await getLatestQualityScorecard({ fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => payload };
  } });

  assert.equal(request.url, "/api/dsp-quality/scorecards/latest");
  assert.equal(request.options.method, "GET");
  assert.deepEqual(result, payload);
});

test("Quality starts in an explicit loading state", () => {
  assert.equal(createDspQualityState().phase, "loading");
  assert.match(qualityLoadingMarkup(), /Caricamento Quality/);
  assert.match(qualityLoadingMarkup(), /aria-busy="true"/);
});

test("empty latest response restores Q4 import UI", () => {
  const state = applyDspQualityEvent(createDspQualityState({ canImport: true }), {
    type: "latest-completed", latest: { available: false },
  });
  assert.equal(state.phase, "empty");
  assert.match(qualityEmptyMarkup(state.canImport), /Importa scorecard/);
});

test("available latest response becomes the persisted overview source", () => {
  const state = applyDspQualityEvent(createDspQualityState({ canImport: true }), {
    type: "latest-completed", latest: latest(),
  });
  assert.equal(state.phase, "available");
  assert.equal(state.latest.scorecard.revision_id, "revision-id");
});

test("persisted overview renders overall standing before score and rank", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.ok(markup.indexOf("Overall Standing") < markup.indexOf("Overall Score"));
  assert.ok(markup.indexOf("Overall Score") < markup.indexOf("Rank</span>"));
  assert.match(markup, /Poor/);
  assert.match(markup, /45\.41/);
  assert.match(markup, />4</);
});

test("persisted overview renders rank WoW as an objective signed value", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /Rank WoW[\s\S]*-1/);
  assert.doesNotMatch(markup, /miglior|peggior|trend/gi);
});

test("persisted overview renders week year DSP and station", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /DSP-READ/);
  assert.match(markup, /ST-READ/);
  assert.match(markup, /Week 47 \/ 2025/);
});

test("focus areas are a semantic ordered list", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /<ol>/);
  assert.match(markup, /Delivery Success Conditions/);
  assert.match(markup, /Delivery Completion Rate/);
  assert.match(markup, /CDF DPMO/);
});

test("section standings render persisted labels and textual standing", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /Compliance and Safety[\s\S]*Fantastic/);
  assert.match(markup, /Delivery Quality &amp; SWC[\s\S]*Poor/);
  assert.match(markup, /Capacity[\s\S]*Fantastic/);
});

test("persisted overview renders transporter DSP metric and WH counts", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /Transporter[\s\S]*159/);
  assert.match(markup, /Metriche DSP[\s\S]*18/);
  assert.match(markup, /Eccezioni WH[\s\S]*0/);
});

test("persisted overview renders compact mapping counts", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /Riconosciuti[\s\S]*8/);
  assert.match(markup, /Da associare[\s\S]*150/);
  assert.match(markup, /Ambigui[\s\S]*1/);
});

test("source traceability includes filename import time and template", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /weekly-scorecard\.pdf/);
  assert.match(markup, /Template[\s\S]*3\.0/);
  assert.match(markup, /Importata/);
  assert.doesNotMatch(markup, /fingerprint/i);
});

test("post-import controller reloads latest instead of retaining preview truth", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /commit\(\{ type: "import-completed", result \}\);[\s\S]*await loadLatest\(\{ notice: "Scorecard importata" \}\)/);
  assert.match(controller, /getLatestQualityScorecard/);
});

test("latest load failure exposes a discrete retry", () => {
  const markup = qualityLatestErrorMarkup("Servizio temporaneamente non disponibile.");
  assert.match(markup, /Quality temporaneamente non disponibile/);
  assert.match(markup, /data-quality-retry>Riprova/);
});

test("retry action calls latest loader", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /data-quality-retry[\s\S]*void loadLatest\(\)/);
});

test("existing scorecard keeps secondary import CTA for writers", () => {
  assert.match(qualityAvailableMarkup(availableView()), /Importa nuova scorecard/);
  assert.match(qualityAvailableMarkup(availableView()), /data-quality-import-open/);
});

test("read-only view does not expose import CTA", () => {
  const markup = qualityAvailableMarkup(availableView({ canImport: false }));
  assert.doesNotMatch(markup, /Importa nuova scorecard/);
});

test("Metriche hands off to the Q6 lazy loading state", () => {
  const markup = qualityAvailableMarkup(availableView({ section: "metrics" }));
  assert.match(markup, /Caricamento metriche/);
  assert.doesNotMatch(markup, /Analisi metriche disponibile nel prossimo step\./);
  assert.doesNotMatch(markup, /canvas|chart|trend/i);
});

test("Driver remains the approved Q5 placeholder", () => {
  const markup = qualityAvailableMarkup(availableView({ section: "drivers" }));
  assert.match(markup, /Performance driver disponibile nel prossimo step\./);
  assert.doesNotMatch(markup, /ranking|coaching/i);
});

test("Quality week context does not read DSP operation date", async () => {
  const qualityFiles = await Promise.all([
    "assets/js/modules/dsp-quality/index.js",
    "assets/js/modules/dsp-quality/state.js",
    "assets/js/modules/dsp-quality/presenter.js",
  ].map(source));
  assert.doesNotMatch(qualityFiles.join("\n"), /dspOperationDate|operation_date/);
});

test("switching DSP tabs keeps Operations controller state isolated", async () => {
  const shell = await source("assets/js/modules/dsp-shell/index.js");
  assert.match(shell, /initDspWorkspace\(\)/);
  assert.match(shell, /nodes\.operations\.hidden/);
  assert.doesNotMatch(shell, /createDspWorkspaceState|date-changed/);
});

test("mobile Quality overview is vertical and has no fixed canvas", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.dsp-quality-overall[\s\S]*grid-template-columns: 1fr/);
  assert.doesNotMatch(css, /min-width:\s*[4-9]\d{2}px/);
});

test("standing remains textual and is not communicated only through color", () => {
  const markup = qualityAvailableMarkup(availableView());
  assert.match(markup, /Overall Standing[\s\S]*Poor/);
  assert.match(markup, /data-standing="poor"/);
});

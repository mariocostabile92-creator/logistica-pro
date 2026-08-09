import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  effectiveMetricStatus,
  filterQualityMetrics,
  metricValueLabel,
  qualityMetricsMarkup,
} from "../assets/js/modules/dsp-quality/metrics-presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
} from "../assets/js/modules/dsp-quality/state.js";


const root = new URL("../", import.meta.url);
const source = path => readFile(new URL(path, root), "utf8");


function metric(overrides = {}) {
  const base = {
    metric_key: "delivery_completion_rate",
    label: "Delivery Completion Rate (DCR)",
    category: "quality",
    value_type: "percentage",
    unit: "percent",
    direction: "HIGHER_IS_BETTER",
    current: {
      raw_value: "96.93%",
      numeric_value: 96.93,
      text_value: null,
      value_state: "PRESENT",
      rating: "Poor",
      compliance_state: null,
    },
    standard: {
      target: 97.9,
      minimum: 97,
      raw_target: "97.9%",
      raw_minimum: "97%",
      standard_available: true,
    },
    previous: {
      available: true,
      week: 46,
      year: 2025,
      numeric_value: 95.5,
      text_value: null,
      rating: "Poor",
    },
    delta: {
      numeric_delta: 1.43,
      direction_adjusted_improvement: "improved",
    },
    status: { target_status: "BELOW_TARGET", minimum_status: "BELOW_MINIMUM" },
  };
  return {
    ...base,
    ...overrides,
    current: { ...base.current, ...(overrides.current || {}) },
    standard: { ...base.standard, ...(overrides.standard || {}) },
    previous: { ...base.previous, ...(overrides.previous || {}) },
    delta: { ...base.delta, ...(overrides.delta || {}) },
    status: { ...base.status, ...(overrides.status || {}) },
  };
}


function data(metrics = [metric()]) {
  return {
    available: true,
    metrics_available: true,
    current_period: { week: 47, year: 2025 },
    previous_period: { week: 46, year: 2025 },
    previous_available: true,
    summary: { evaluatable: 12, target_met: 7, attention: 5 },
    categories: [...new Set(metrics.map(item => item.category))],
    metrics,
  };
}


const markup = (metrics = [metric()], extra = {}) => qualityMetricsMarkup({
  phase: "available",
  data: data(metrics),
  filter: "all",
  search: "",
  ...extra,
});


test("Metriche is no longer the approved Q5 placeholder", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.doesNotMatch(presenter, /Analisi metriche disponibile nel prossimo step/);
  assert.match(presenter, /qualityMetricsMarkup/);
});

test("metrics state starts idle and exposes loading", () => {
  let state = createDspQualityState();
  assert.equal(state.metrics.phase, "idle");
  state = applyDspQualityEvent(state, { type: "metrics-started" });
  assert.equal(state.metrics.phase, "loading");
  assert.match(qualityMetricsMarkup(state.metrics), /Caricamento metriche/);
});

test("category grouping uses semantic headings", () => {
  const html = markup([
    metric(),
    metric({ metric_key: "vsa", label: "VSA", category: "compliance" }),
  ]);
  assert.match(html, /<h3 id="quality-category-quality">Quality<\/h3>/);
  assert.match(html, /Compliance/);
});

test("current value is rendered from persisted raw value", () => {
  assert.match(markup(), /96\.93%/);
});

test("Amazon rating is visible and remains distinct", () => {
  assert.match(markup(), /dsp-quality-rating">Poor/);
});

test("target and minimum are visible", () => {
  const html = markup();
  assert.match(html, /Target[\s\S]*97\.9%/);
  assert.match(html, /Minimum[\s\S]*97%/);
});

test("TARGET_MET has a textual label", () => {
  assert.match(markup([metric({ status: { target_status: "TARGET_MET", minimum_status: "TARGET_MET" } })]), /Target raggiunto/);
});

test("BELOW_TARGET has a textual label", () => {
  assert.match(markup([metric({ status: { target_status: "BELOW_TARGET", minimum_status: "TARGET_MET" } })]), /Sotto target/);
});

test("BELOW_MINIMUM takes visible priority", () => {
  assert.equal(effectiveMetricStatus(metric()), "BELOW_MINIMUM");
  assert.match(markup(), /Sotto minimo/);
});

test("NO_STANDARD has a textual label", () => {
  assert.match(markup([metric({ status: { target_status: "NO_STANDARD", minimum_status: "NO_STANDARD" } })]), /Standard non disponibile/);
});

test("NOT_AVAILABLE is never rendered as null", () => {
  assert.equal(metricValueLabel({ value_state: "NOT_AVAILABLE" }), "Non disponibile");
});

test("NOT_APPLICABLE has explicit copy", () => {
  assert.equal(metricValueLabel({ value_state: "NOT_APPLICABLE" }), "Non applicabile");
});

test("MISSING has explicit copy", () => {
  assert.equal(metricValueLabel({ value_state: "MISSING" }), "Dato mancante");
});

test("previous value and explicit period are visible", () => {
  const html = markup();
  assert.match(html, /vs Week 46 · 2025/);
  assert.match(html, /Precedente <strong>95\.5/);
});

test("improved comparison is textual and includes delta", () => {
  const html = markup();
  assert.match(html, /\+1\.43/);
  assert.match(html, /Migliorata/);
});

test("worsened comparison is textual", () => {
  assert.match(markup([metric({ delta: { numeric_delta: -1, direction_adjusted_improvement: "worsened" } })]), /Peggiorata/);
});

test("unchanged comparison is textual", () => {
  assert.match(markup([metric({ delta: { numeric_delta: 0, direction_adjusted_improvement: "unchanged" } })]), /Invariata/);
});

test("lower-is-better improvement preserves the negative numeric delta", () => {
  const html = markup([metric({
    metric_key: "dnr",
    label: "DNR DPMO",
    direction: "LOWER_IS_BETTER",
    delta: { numeric_delta: -300, direction_adjusted_improvement: "improved" },
  })]);
  assert.match(html, /-300/);
  assert.match(html, /Migliorata/);
});

test("attention filter keeps only below target or minimum", () => {
  const result = filterQualityMetrics([
    metric(),
    metric({ label: "POD", status: { target_status: "TARGET_MET", minimum_status: "TARGET_MET" } }),
  ], "attention");
  assert.deepEqual(result.map(item => item.label), ["Delivery Completion Rate (DCR)"]);
});

test("target filter keeps only target met", () => {
  const result = filterQualityMetrics([
    metric(),
    metric({ label: "POD", status: { target_status: "TARGET_MET", minimum_status: "TARGET_MET" } }),
  ], "target");
  assert.deepEqual(result.map(item => item.label), ["POD"]);
});

test("search is case-insensitive and uses metric label only", () => {
  assert.equal(filterQualityMetrics([metric()], "all", "completion").length, 1);
  assert.equal(filterQualityMetrics([metric()], "all", "technical-key").length, 0);
});

test("summary is limited to exactly three KPIs", () => {
  const html = markup();
  assert.match(html, /Metriche valutabili[\s\S]*12/);
  assert.match(html, /Target raggiunti[\s\S]*7/);
  assert.match(html, /Da attenzionare[\s\S]*5/);
  assert.doesNotMatch(html, /Overall Score/);
});

test("error state exposes a local retry", () => {
  const html = qualityMetricsMarkup({ phase: "error", error: "Errore sicuro" });
  assert.match(html, /Metriche temporaneamente non disponibili/);
  assert.match(html, /data-quality-metrics-retry/);
});

test("no previous scorecard has the approved neutral message", () => {
  const payload = data();
  payload.previous_available = false;
  payload.previous_period = null;
  const html = qualityMetricsMarkup({ phase: "available", data: payload, filter: "all", search: "" });
  assert.match(html, /Nessuna scorecard precedente disponibile per il confronto\./);
});

test("scorecard without metrics has the approved empty state", () => {
  const payload = data([]);
  payload.metrics_available = false;
  assert.match(qualityMetricsMarkup({ phase: "available", data: payload, filter: "all", search: "" }), /Nessuna metrica disponibile per questa scorecard/);
});

test("metrics endpoint is lazy and requested only on metrics tab", async () => {
  const [api, controller] = await Promise.all([
    source("assets/js/modules/dsp-quality/api.js"),
    source("assets/js/modules/dsp-quality/index.js"),
  ]);
  assert.match(api, /scorecards\/latest\/metrics/);
  assert.match(controller, /section === "metrics"[\s\S]*loadMetrics/);
  assert.doesNotMatch(controller, /loadLatest[\s\S]{0,120}getQualityMetrics/);
});

test("mobile 390 layout is one column with bounded controls", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-metric-grid[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /dsp-quality-metrics-controls button[\s\S]*min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});

test("Q5 Panoramica remains the persisted overview", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.match(presenter, /persistedOverview\(view\.latest\)/);
  assert.match(presenter, /Overall Standing/);
});

test("Driver placeholder is removed by Q7 without changing Metriche", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.match(presenter, /qualityDriversMarkup/);
  assert.doesNotMatch(presenter, /Performance driver disponibile nel prossimo step\./);
});

test("metrics controller supports filter search retry and cache invalidation", async () => {
  const [controller, state] = await Promise.all([
    source("assets/js/modules/dsp-quality/index.js"),
    source("assets/js/modules/dsp-quality/state.js"),
  ]);
  assert.match(controller, /data-quality-metrics-filter/);
  assert.match(controller, /data-quality-metrics-search/);
  assert.match(controller, /data-quality-metrics-retry/);
  assert.match(state, /latest-started[\s\S]*phase: "idle"/);
});

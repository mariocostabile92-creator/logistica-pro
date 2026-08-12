import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getQualityDriverHistory } from "../assets/js/modules/dsp-quality/api.js";
import {
  buildHistoryChart,
  defaultHistoryMetricKey,
  qualityDriverHistoryMarkup,
} from "../assets/js/modules/dsp-quality/driver-history-presenter.js";
import { qualityAttentionMarkup } from "../assets/js/modules/dsp-quality/attention-presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function metric(key, label, value, comparison, overrides = {}) {
  return {
    metric_key: key,
    label,
    unit: key === "photo_on_delivery" ? "%" : key.includes("dpmo") ? "DPMO" : null,
    direction: key.includes("dpmo") ? "LOWER_IS_BETTER" : "HIGHER_IS_BETTER",
    value: {
      raw_value: value == null ? null : String(value),
      numeric_value: value,
      text_value: null,
      value_state: value == null ? "MISSING" : "PRESENT",
    },
    comparison,
    numeric_delta: value == null ? null : -1,
    consecutive_worsening_comparisons: 0,
    consecutive_improving_comparisons: 0,
    recurring: false,
    recovery: false,
    status: "NO_DRIVER_STANDARD",
    ...overrides,
  };
}


function entry(week, pod, cdf, overrides = {}) {
  const comparison = week === 42 ? "NOT_COMPARABLE" : "WORSENED";
  return {
    scorecard_id: `score-${week}`,
    revision_id: `revision-${week}`,
    year: 2026,
    week,
    imported_at: `2026-08-${String(week - 35).padStart(2, "0")}T10:00:00Z`,
    weekly_status: week === 42 ? "SENZA_STORICO" : "DA_MIGLIORARE",
    weekly_focus: [{
      metric_key: "photo_on_delivery",
      label: "Proof of Delivery",
      current: pod,
      previous: null,
      unit: "%",
      direction: comparison.toLowerCase(),
      reason: "POD in peggioramento.",
    }],
    reasons: ["Confronto con la precedente scorecard disponibile."],
    customer_escalations: week === 46 ? 1 : 0,
    metrics: [
      metric("delivery_completion_rate", "Delivery Completion Rate", 98, "UNCHANGED"),
      metric("photo_on_delivery", "Photo-On-Delivery", pod, comparison, {
        consecutive_worsening_comparisons: week === 46 ? 3 : 0,
        recurring: week === 46,
      }),
      metric("customer_delivery_feedback_dpmo", "Customer Delivery Feedback DPMO", cdf, week === 42 ? "NOT_COMPARABLE" : "IMPROVED", {
        consecutive_improving_comparisons: week === 46 ? 3 : 0,
      }),
      metric("customer_escalations_count", "Customer Escalations", week === 46 ? 1 : 0, week === 42 ? "NOT_COMPARABLE" : "UNCHANGED"),
    ],
    ...overrides,
  };
}


function historyData() {
  const timeline = [
    entry(42, 99.5, 5000),
    entry(43, 99, 4500),
    entry(45, 98.2, 4000),
    entry(46, 97.5, 3200, { weekly_status: "DA_ATTENZIONARE" }),
  ];
  return {
    available: true,
    transporter_external_id: "A-TRANSPORTER-01",
    workforce_member_id: 7,
    workforce_display_name: "Mario Rossi",
    mapping_status: "MATCHED",
    source_provider: "amazon",
    dsp_identifier: "PROF",
    station: "DLO2",
    anchor_scorecard_id: "score-46",
    anchor_period: { year: 2026, week: 46 },
    summary: {
      weeks_available: 4,
      first_period: { year: 2026, week: 42 },
      latest_period: { year: 2026, week: 46 },
      current_status: "DA_ATTENZIONARE",
      current_focus: timeline.at(-1).weekly_focus,
      recurring_worsening_metrics: [{
        metric_key: "photo_on_delivery",
        label: "Photo-On-Delivery",
        direction: "HIGHER_IS_BETTER",
        consecutive_worsening_comparisons: 3,
        consecutive_improving_comparisons: 0,
        recurring: true,
        recovery: false,
      }],
      recurring_improving_metrics: [{
        metric_key: "customer_delivery_feedback_dpmo",
        label: "Customer Delivery Feedback DPMO",
        direction: "LOWER_IS_BETTER",
        consecutive_worsening_comparisons: 0,
        consecutive_improving_comparisons: 3,
        recurring: false,
        recovery: true,
      }],
      recent_customer_escalations: 1,
    },
    metric_trends: [{
      metric_key: "customer_delivery_feedback_dpmo",
      label: "Customer Delivery Feedback DPMO",
      direction: "LOWER_IS_BETTER",
      consecutive_worsening_comparisons: 0,
      consecutive_improving_comparisons: 3,
      recurring: false,
      recovery: true,
    }],
    timeline,
  };
}


test("history API carries selected Q9 scorecard and one Transporter ID", async () => {
  let requested = "";
  await getQualityDriverHistory("A/01", {
    scorecardId: "score-46",
    fetcher: async url => {
      requested = String(url);
      return { ok: true, json: async () => ({ available: true }) };
    },
  });
  assert.match(requested, /drivers\/A%2F01\/history\?/);
  assert.match(requested, /scorecard_id=score-46/);
  assert.match(requested, /limit=52/);
});


test("header renders readable identity, Transporter ID, current status and focus", () => {
  const markup = qualityDriverHistoryMarkup({
    phase: "available",
    data: historyData(),
    metricKey: "photo_on_delivery",
  });
  assert.match(markup, /Mario Rossi/);
  assert.match(markup, /A-TRANSPORTER-01/);
  assert.match(markup, /Da attenzionare/);
  assert.match(markup, /Proof of Delivery/);
  assert.match(markup, /W42/);
  assert.match(markup, /W46/);
  assert.doesNotMatch(markup, /Quality Score|Risk Score/);
});


test("timeline keeps real non-consecutive weeks, recurring and escalation evidence", () => {
  const markup = qualityDriverHistoryMarkup({
    phase: "available",
    data: historyData(),
    metricKey: "photo_on_delivery",
  });
  assert.deepEqual(
    [...markup.matchAll(/data-history-week="(\d+)"/g)].map(match => Number(match[1])),
    [42, 43, 45, 46],
  );
  assert.doesNotMatch(markup, /data-history-week="44"/);
  assert.match(markup, /Ricorrente/);
  assert.match(markup, /In recupero/);
  assert.match(markup, /1<\/strong> Customer Escalation/);
});


test("metric selector defaults to current focus and chart uses real values", () => {
  const data = historyData();
  assert.equal(defaultHistoryMetricKey(data), "photo_on_delivery");
  const chart = buildHistoryChart(data, "photo_on_delivery");
  assert.deepEqual(chart.points.map(point => point.week), [42, 43, 45, 46]);
  assert.deepEqual(chart.points.map(point => point.value), [99.5, 99, 98.2, 97.5]);
  const markup = qualityDriverHistoryMarkup({ phase: "available", data, metricKey: "photo_on_delivery" });
  assert.match(markup, /data-quality-driver-history-metric/);
  assert.doesNotMatch(markup, /target-line|minimum-line|driver-target/);
  assert.match(markup, /Nessun target driver applicato/);
});


test("missing metric is a chart gap and is never converted to zero", () => {
  const data = historyData();
  data.timeline[2].metrics.find(item => item.metric_key === "photo_on_delivery").value.numeric_value = null;
  const chart = buildHistoryChart(data, "photo_on_delivery");
  assert.equal(chart.points[2].value, null);
  assert.equal(chart.segments.length, 2);
  const markup = qualityDriverHistoryMarkup({ phase: "available", data, metricKey: "photo_on_delivery" });
  assert.match(markup, />gap</);
});


test("Q10 detail state preserves selected week and back returns to Attention", () => {
  let state = createDspQualityState();
  state = { ...state, phase: "available", section: "attention", selectedScorecardId: "score-46" };
  state = applyDspQualityEvent(state, { type: "driver-history-started", transporterExternalId: "A-TRANSPORTER-01" });
  state = applyDspQualityEvent(state, {
    type: "driver-history-completed",
    data: historyData(),
    metricKey: "photo_on_delivery",
  });
  assert.equal(state.attention.detail.phase, "available");
  state = applyDspQualityEvent(state, { type: "driver-history-metric-changed", metricKey: "customer_delivery_feedback_dpmo" });
  assert.equal(state.attention.detail.metricKey, "customer_delivery_feedback_dpmo");
  state = applyDspQualityEvent(state, { type: "driver-history-closed" });
  assert.equal(state.attention.detail.phase, "closed");
  assert.equal(state.selectedScorecardId, "score-46");
  assert.equal(state.section, "attention");
});


test("Attention renders Q11 internally without a fifth main tab", async () => {
  const markup = qualityAttentionMarkup({
    phase: "available",
    detail: { phase: "available", data: historyData(), metricKey: "photo_on_delivery" },
  });
  assert.match(markup, /Storico Quality driver/);
  assert.match(markup, /Torna ad Attenzione/);
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.doesNotMatch(presenter, /\["history"|\["andamento"/);
  assert.match(presenter, /\["attention", "Attenzione"\].*\["metrics", "Metriche"\].*\["drivers", "Driver"\]/s);
});


test("controller opens history from Vedi andamento and CSS protects 390px", async () => {
  const [controller, css] = await Promise.all([
    source("assets/js/modules/dsp-quality/index.js"),
    source("assets/css/dsp-quality.css"),
  ]);
  assert.match(controller, /loadDriverHistory\(attentionDriver\)/);
  assert.doesNotMatch(controller, /attentionDriver[\s\S]{0,180}section-changed[\s\S]{0,80}drivers/);
  assert.match(css, /@media \(max-width: 480px\)/);
  assert.match(css, /\.dsp-quality-history-back[^}]*width:\s*100%[^}]*min-height:\s*44px/s);
  assert.match(css, /grid-template-columns:\s*1fr/);
});

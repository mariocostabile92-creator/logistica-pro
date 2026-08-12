import assert from "node:assert/strict";
import test from "node:test";

import { getQualityAttention } from "../assets/js/modules/dsp-quality/api.js";
import { qualityAttentionMarkup } from "../assets/js/modules/dsp-quality/attention-presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
} from "../assets/js/modules/dsp-quality/state.js";


function driver(status, suffix = "1", overrides = {}) {
  return {
    row_id: `row-${suffix}`,
    transporter_external_id: `TID-${suffix}`,
    workforce_member_id: Number(suffix) || null,
    display_name: `Driver ${suffix}`,
    status,
    escalation_present: status === "DA_ATTENZIONARE",
    history_available: status !== "SENZA_STORICO",
    comparable_metrics: 3,
    worsened_metrics: status === "DA_ATTENZIONARE" ? 2 : status === "DA_MIGLIORARE" ? 1 : 0,
    improved_metrics: status === "IN_MIGLIORAMENTO" ? 2 : 0,
    unchanged_metrics: status === "STABILE" ? 3 : 0,
    reasons: [`Motivazione ${suffix}`],
    focus: [{
      metric_key: "delivery_completion_rate",
      label: "Delivery Completion",
      current: 96,
      previous: 98,
      unit: "percent",
      direction: "worsened",
      reason: "98 → 96; metrica peggiorata.",
    }],
    ...overrides,
  };
}


function data(drivers = []) {
  return {
    available: true,
    current_period: { week: 47, year: 2025 },
    previous_period: { week: 45, year: 2025 },
    previous_available: true,
    summary: {
      total_drivers: drivers.length,
      statuses: {
        da_attenzionare: drivers.filter(item => item.status === "DA_ATTENZIONARE").length,
        da_migliorare: drivers.filter(item => item.status === "DA_MIGLIORARE").length,
        in_miglioramento: drivers.filter(item => item.status === "IN_MIGLIORAMENTO").length,
        stabile: drivers.filter(item => item.status === "STABILE").length,
        senza_storico: drivers.filter(item => item.status === "SENZA_STORICO").length,
      },
    },
    dsp_signals: [{
      metric_key: "delivery_completion_rate",
      label: "Delivery Completion Rate",
      current: 96,
      previous: 98,
      delta: -2,
      status: "BELOW_MINIMUM",
      reason: "Valore sotto il minimo persistito per la scorecard.",
    }],
    drivers,
  };
}


test("selected attention API uses the Q9 selected scorecard", async () => {
  let requested = "";
  const result = await getQualityAttention("scorecard-45", {
    fetcher: async url => {
      requested = String(url);
      return { ok: true, json: async () => ({ available: true }) };
    },
  });
  assert.equal(result.available, true);
  assert.match(requested, /scorecards\/scorecard-45\/attention$/);
  assert.doesNotMatch(requested, /latest/);
});


test("state supports attention loading, filters, search and scorecard reset", () => {
  let state = createDspQualityState();
  state = applyDspQualityEvent(state, { type: "attention-started" });
  assert.equal(state.attention.phase, "loading");
  state = applyDspQualityEvent(state, { type: "attention-completed", data: data([]) });
  state = applyDspQualityEvent(state, { type: "attention-filter-changed", filter: "STABILE" });
  state = applyDspQualityEvent(state, { type: "attention-search-changed", search: "Mario" });
  assert.equal(state.attention.filter, "STABILE");
  assert.equal(state.attention.search, "Mario");
  state = applyDspQualityEvent(state, { type: "scorecard-selection-changed", scorecardId: "new" });
  assert.equal(state.attention.phase, "idle");
  assert.equal(state.attention.data, null);
});


test("attention renders the five exclusive states, reasons, focus and Transporter deep link", () => {
  const drivers = [
    driver("DA_ATTENZIONARE", "1"),
    driver("DA_MIGLIORARE", "2"),
    driver("IN_MIGLIORAMENTO", "3"),
    driver("STABILE", "4"),
    driver("SENZA_STORICO", "5"),
  ];
  const markup = qualityAttentionMarkup({ phase: "available", data: data(drivers), filter: "all", search: "" });
  for (const label of ["Da attenzionare", "Da migliorare", "In miglioramento", "Stabile", "Senza storico"]) {
    assert.match(markup, new RegExp(label));
  }
  assert.match(markup, /Delivery Completion/);
  assert.match(markup, /Motivazione 1/);
  assert.match(markup, /data-quality-attention-driver="TID-1"/);
  assert.match(markup, /Attenzioni DSP/);
});


test("status filter and name or Transporter search are applied client-side", () => {
  const drivers = [driver("STABILE", "1", { display_name: "Mario Rossi" }), driver("DA_MIGLIORARE", "2")];
  const byStatus = qualityAttentionMarkup({ phase: "available", data: data(drivers), filter: "STABILE", search: "" });
  assert.match(byStatus, /Mario Rossi/);
  assert.doesNotMatch(byStatus, /Driver 2/);
  const byTid = qualityAttentionMarkup({ phase: "available", data: data(drivers), filter: "all", search: "tid-2" });
  assert.match(byTid, /Driver 2/);
  assert.doesNotMatch(byTid, /Mario Rossi/);
});


test("initial view limits each status category to ten cards", () => {
  const drivers = Array.from({ length: 12 }, (_, index) => driver("STABILE", String(index + 1)));
  const markup = qualityAttentionMarkup({ phase: "available", data: data(drivers), filter: "all", search: "" });
  assert.equal((markup.match(/dsp-quality-attention-card"/g) || []).length, 10);
});


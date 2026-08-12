import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  closeQualityFollowup,
  createQualityFollowup,
  getQualityFollowups,
} from "../assets/js/modules/dsp-quality/api.js";
import { qualityAttentionMarkup } from "../assets/js/modules/dsp-quality/attention-presenter.js";
import { qualityDriverHistoryMarkup } from "../assets/js/modules/dsp-quality/driver-history-presenter.js";
import {
  followupDialogMarkup,
  followupListMarkup,
  followupSummaryMarkup,
} from "../assets/js/modules/dsp-quality/followup-presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function followup(overrides = {}) {
  return {
    id: "followup-1",
    transporter_external_id: "T-ID-1",
    workforce_member_id: 4,
    driver_display_name: "Yassine Zyadi",
    metric_key: "delivery_completion_rate",
    metric_label: "Delivery Completion Rate (DCR)",
    metric_unit: "percent",
    baseline_direction: "HIGHER_IS_BETTER",
    baseline_status: "DA_MIGLIORARE",
    baseline: { scorecard_id: "score-46", year: 2026, week: 46, value: 98.04 },
    note: "Confronto con il driver su completamento consegne.",
    status: "IMPROVED",
    created_by: "manager",
    created_at: "2026-08-12T10:00:00Z",
    review: {
      state: "COMPARABLE",
      result: "IMPROVED",
      period: { scorecard_id: "score-47", year: 2026, week: 47, value: 99.02 },
      delta: 0.98,
      delta_unit: "pp",
      message: "La metrica è migliorata rispetto alla baseline.",
    },
    closed_at: null,
    closed_by: null,
    close_note: null,
    ...overrides,
  };
}


function followups(items = [followup()]) {
  return {
    phase: "available",
    data: {
      items,
      summary: { open: items.filter(item => item.status !== "CLOSED").length, review_due: 0, improved: 1, worsened: 0, unchanged: 0, closed: 0 },
    },
    dialog: { phase: "closed" },
  };
}


function attention(overrides = {}) {
  return {
    available: true,
    current_period: { week: 46, year: 2026 },
    summary: { statuses: {}, total_drivers: 1 },
    dsp_signals: [],
    drivers: [{
      transporter_external_id: "T-ID-1",
      display_name: "Yassine Zyadi",
      status: "DA_MIGLIORARE",
      worsened_metrics: 1,
      improved_metrics: 0,
      comparable_metrics: 1,
      reasons: ["Una metrica peggiorata."],
      focus: [{ metric_key: "delivery_completion_rate", label: "DCR", current: 98.04, previous: 99, unit: "%", reason: "DCR peggiorata." }],
    }],
    ...overrides,
  };
}


function history() {
  const metric = {
    metric_key: "delivery_completion_rate",
    label: "DCR",
    unit: "%",
    direction: "HIGHER_IS_BETTER",
    value: { numeric_value: 98.04 },
    comparison: "WORSENED",
    numeric_delta: -0.96,
    recurring: false,
    recovery: false,
  };
  return {
    available: true,
    transporter_external_id: "T-ID-1",
    workforce_display_name: "Yassine Zyadi",
    summary: {
      weeks_available: 2,
      first_period: { year: 2026, week: 46 },
      latest_period: { year: 2026, week: 47 },
      current_status: "IN_MIGLIORAMENTO",
      current_focus: [{ metric_key: "delivery_completion_rate", label: "DCR", current: 99.02, previous: 98.04, unit: "%", reason: "DCR migliorata." }],
      recurring_worsening_metrics: [],
      recurring_improving_metrics: [],
      recent_customer_escalations: 0,
    },
    metric_trends: [],
    timeline: [
      { scorecard_id: "score-46", year: 2026, week: 46, weekly_status: "DA_MIGLIORARE", weekly_focus: [], reasons: [], metrics: [metric] },
      { scorecard_id: "score-47", year: 2026, week: 47, weekly_status: "IN_MIGLIORAMENTO", weekly_focus: [], reasons: [], metrics: [{ ...metric, value: { numeric_value: 99.02 }, comparison: "IMPROVED" }] },
    ],
  };
}


test("follow-up APIs use the Q12 endpoints and payload", async () => {
  const calls = [];
  const fetcher = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    return { ok: true, json: async () => ({ items: [] }) };
  };
  await getQualityFollowups({ transporterExternalId: "T/1", fetcher });
  await createQualityFollowup({ transporter_external_id: "T/1", scorecard_id: "S46", metric_key: "photo_on_delivery", note: "Nota" }, { fetcher });
  await closeQualityFollowup("F/1", { note: "Chiusa" }, { fetcher });
  assert.match(calls[0].url, /followups\?transporter_external_id=T%2F1/);
  assert.equal(calls[1].options.method, "POST");
  assert.match(calls[1].options.body, /photo_on_delivery/);
  assert.match(calls[2].url, /followups\/F%2F1\/close/);
});


test("Q10 focus exposes create CTA and existing open marker without a new tab", async () => {
  const empty = qualityAttentionMarkup({ phase: "available", data: attention(), followups: followups([]), canWrite: true });
  const existing = qualityAttentionMarkup({ phase: "available", data: attention(), followups: followups(), canWrite: true });
  assert.match(empty, /Crea follow-up/);
  assert.match(empty, /data-quality-followup-create="delivery_completion_rate"/);
  assert.match(existing, /Follow-up aperto/);
  assert.doesNotMatch(existing, /Crea follow-up/);
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.doesNotMatch(presenter, /\["followups"/);
});


test("create dialog shows driver metric baseline week and note", () => {
  const markup = followupDialogMarkup({
    phase: "editing",
    mode: "create",
    note: "Confronto operativo",
    context: { driverDisplayName: "Yassine Zyadi", metricLabel: "DCR", current: 98.04, unit: "%", periodLabel: "Week 46 · 2026" },
  }, { canWrite: true });
  assert.match(markup, /Yassine Zyadi/);
  assert.match(markup, /DCR/);
  assert.match(markup, /98,04%/);
  assert.match(markup, /Week 46/);
  assert.match(markup, /Confronto operativo/);
});


test("list renders improved worsened unchanged and insufficient review states", () => {
  const items = [
    followup(),
    followup({ id: "w", status: "WORSENED", review: { ...followup().review, result: "WORSENED", message: "Peggiorata." } }),
    followup({ id: "u", status: "UNCHANGED", review: { ...followup().review, result: "UNCHANGED", message: "Invariata." } }),
    followup({ id: "m", status: "OPEN", review: { state: "MISSING_METRIC", result: null, period: { scorecard_id: "s47", week: 47, year: 2026, value: null }, delta: null, delta_unit: null, message: "Dati insufficienti per la verifica." } }),
  ];
  const markup = followupListMarkup(followups(items));
  assert.match(markup, /Migliorata/);
  assert.match(markup, /Peggiorata/);
  assert.match(markup, /Invariata/);
  assert.match(markup, /Dati insufficienti/);
  assert.match(markup, /\+0,98 pp/);
});


test("summary exposes the four operational counters", () => {
  const markup = followupSummaryMarkup({ data: { summary: { open: 4, review_due: 2, improved: 1, worsened: 1 } } });
  assert.match(markup, /Follow-up aperti<\/dt><dd>4/);
  assert.match(markup, /Da verificare<\/dt><dd>2/);
  assert.match(markup, /Migliorati<\/dt><dd>1/);
  assert.match(markup, /Peggiorati<\/dt><dd>1/);
});


test("Q11 renders follow-up section and baseline/review events on the real weeks", () => {
  const markup = qualityDriverHistoryMarkup({ phase: "available", data: history(), metricKey: "delivery_completion_rate", followups: followups(), canWrite: true });
  assert.match(markup, /Follow-up Quality/);
  assert.match(markup, /Baseline W46/);
  assert.match(markup, /Review W47/);
  assert.match(markup, /Follow-up Delivery Completion Rate \(DCR\).*aperto/s);
  assert.match(markup, /Follow-up Delivery Completion Rate \(DCR\).*Migliorata/s);
});


test("state supports create close and detail lifecycle", () => {
  let state = createDspQualityState({ canImport: true });
  state = applyDspQualityEvent(state, { type: "followup-create-opened", context: { metricKey: "dcr" } });
  state = applyDspQualityEvent(state, { type: "followup-note-changed", note: "Nota" });
  state = applyDspQualityEvent(state, { type: "followup-save-started" });
  state = applyDspQualityEvent(state, { type: "followup-detail-completed", item: followup() });
  assert.equal(state.followups.dialog.mode, "detail");
  assert.equal(state.followups.dialog.item.status, "IMPROVED");
  state = applyDspQualityEvent(state, { type: "followup-close-note-changed", note: "Conclusa" });
  assert.equal(state.followups.dialog.closeNote, "Conclusa");
  state = applyDspQualityEvent(state, { type: "followup-dialog-closed" });
  assert.equal(state.followups.dialog.phase, "closed");
});


test("close CTA is manual and shown only after comparable review", () => {
  const comparable = followupDialogMarkup({ phase: "available", mode: "detail", item: followup(), closeNote: "" }, { canWrite: true });
  const waiting = followupDialogMarkup({ phase: "available", mode: "detail", item: followup({ status: "OPEN", review: { state: "WAITING_SCORECARD", result: null, period: null, message: "In attesa." } }), closeNote: "" }, { canWrite: true });
  assert.match(comparable, /Chiudi follow-up/);
  assert.doesNotMatch(waiting, /data-quality-followup-close/);
});


test("390px CSS protects modal actions and cards from overflow", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 30em\)[\s\S]*\.dsp-quality-followup-list[\s\S]*grid-template-columns:\s*1fr/);
  assert.match(css, /\.quality-followup-dialog > footer button[\s\S]*min-height:\s*44px/);
  assert.match(css, /width:\s*min\(38rem, 100%\)/);
});

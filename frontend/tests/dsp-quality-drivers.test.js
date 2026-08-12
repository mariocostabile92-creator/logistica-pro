import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getLatestQualityDrivers } from "../assets/js/modules/dsp-quality/api.js";
import {
  driverDisplayName,
  driverMetricValue,
  filterQualityDrivers,
  qualityDriversMarkup,
  sortQualityDrivers,
} from "../assets/js/modules/dsp-quality/drivers-presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


const METRICS = [
  ["delivered", "Delivered", "135", 135, "NO_DIRECTION"],
  ["delivery_completion_rate", "Delivery Completion Rate (DCR)", "92.47%", 92.47, "HIGHER_IS_BETTER"],
  ["delivery_success_conditions_dpmo", "Delivery Success Conditions (DSC DPMO)", "18", 18, "LOWER_IS_BETTER"],
  ["lost_on_road_dpmo", "Lost on Road (LoR) DPMO", "0", 0, "LOWER_IS_BETTER"],
  ["photo_on_delivery", "Photo-On-Delivery", "96.88%", 96.88, "HIGHER_IS_BETTER"],
  ["contact_compliance", "Contact Compliance", "88%", 88, "HIGHER_IS_BETTER"],
  ["customer_escalations_count", "Customer Escalations", "1", 1, "LOWER_IS_BETTER"],
  ["customer_delivery_feedback_dpmo", "Customer Delivery Feedback DPMO", "29630", 29630, "LOWER_IS_BETTER"],
];


function metric([key, label, raw, numeric, direction], overrides = {}) {
  return {
    metric_key: key,
    label,
    value_type: key === "delivered" || key === "customer_escalations_count" ? "count" : "percentage",
    unit: key.includes("dpmo") ? "dpmo" : null,
    direction,
    current: { raw_value: raw, numeric_value: numeric, text_value: null, value_state: "PRESENT" },
    previous: { available: true, week: 46, year: 2025, raw_value: raw, numeric_value: numeric - 1, text_value: null, value_state: "PRESENT" },
    delta: { numeric_delta: 1, direction_adjusted_improvement: direction === "LOWER_IS_BETTER" ? "worsened" : direction === "NO_DIRECTION" ? "unknown" : "improved" },
    status: "NO_DRIVER_STANDARD",
    ...overrides,
  };
}


function row(index = 1, overrides = {}) {
  const status = overrides.mapping_status || "UNMAPPED";
  return {
    row_id: `row-${index}`,
    row_index: index,
    transporter_external_id: overrides.transporter_external_id || `A13GR86JNE${String(index).padStart(4, "0")}`,
    mapping_status: status,
    workforce_member_id: status === "MATCHED" ? overrides.workforce_member_id || index : null,
    workforce_display_name: status === "MATCHED" ? overrides.workforce_display_name || `Driver ${index}` : null,
    metrics: METRICS.map(item => metric(item)),
    ...overrides,
  };
}


function data(rows = [row(1)]) {
  return {
    available: true,
    drivers_available: rows.length > 0,
    current_period: { week: 47, year: 2025 },
    previous_period: { week: 46, year: 2025 },
    previous_available: true,
    summary: {
      total: rows.length,
      matched: rows.filter(item => item.mapping_status === "MATCHED").length,
      unmapped: rows.filter(item => item.mapping_status === "UNMAPPED").length,
      ambiguous: rows.filter(item => item.mapping_status === "AMBIGUOUS").length,
    },
    rows,
  };
}


function markup(rows = [row(1)], extra = {}) {
  return qualityDriversMarkup({
    phase: "available",
    data: data(rows),
    filter: "all",
    search: "",
    sort: { key: "row_index", direction: "asc" },
    selectedRowId: null,
    ...extra,
  });
}


test("Driver tab is a real Q7 read model rather than a placeholder", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.match(presenter, /qualityDriversMarkup/);
  assert.doesNotMatch(presenter, /Performance driver disponibile nel prossimo step/);
});

test("drivers state exposes explicit loading", () => {
  let state = createDspQualityState();
  state = applyDspQualityEvent(state, { type: "drivers-started" });
  assert.equal(state.drivers.phase, "loading");
  assert.match(qualityDriversMarkup(state.drivers), /Caricamento performance driver/);
});

test("159 imported rows render without pagination assumptions", () => {
  const rows = Array.from({ length: 159 }, (_, index) => row(index + 1));
  const html = markup(rows);
  assert.equal((html.match(/data-quality-driver-row=/g) || []).length, 159);
  assert.match(html, /Transporter totali[\s\S]*159/);
});

test("matched row shows Workforce name and Transporter ID", () => {
  const matched = row(1, { mapping_status: "MATCHED", workforce_display_name: "Alessandro Facchetti", transporter_external_id: "A13GR86JNE2BY9" });
  const html = markup([matched]);
  assert.match(html, /Alessandro Facchetti/);
  assert.match(html, /A13GR86JNE2BY9/);
  assert.equal(driverDisplayName(matched), "Alessandro Facchetti");
});

test("unmapped row has readable Transporter identity and Da associare", () => {
  const html = markup([row(1, { mapping_status: "UNMAPPED", transporter_external_id: "UNMAPPED-ID" })]);
  assert.match(html, /Transporter UNMAPPED-ID/);
  assert.match(html, /Da associare/);
});

test("ambiguous mapping is textual and never selects a driver", () => {
  const html = markup([row(1, { mapping_status: "AMBIGUOUS", transporter_external_id: "AMB-ID" })]);
  assert.match(html, /Associazione ambigua/);
  assert.doesNotMatch(html, /Apri driver Workforce/);
});

test("main list renders DCR POD CC DSC CDF CE and Delivered", () => {
  const html = markup();
  for (const token of ["92.47%", "96.88%", "88%", "18", "29630", "135"]) {
    assert.match(html, new RegExp(token.replace(".", "\\.")));
  }
  assert.match(html, />1<\/td>/);
});

test("missing values never render null NaN or undefined", () => {
  const missing = row();
  missing.metrics[0] = metric(METRICS[0], { current: { raw_value: null, numeric_value: null, text_value: null, value_state: "MISSING" } });
  const html = markup([missing]);
  assert.match(html, /Dato mancante/);
  assert.doesNotMatch(html, />null<|>NaN<|>undefined</);
  assert.equal(driverMetricValue(missing.metrics[0]), "Dato mancante");
});

test("search finds matched driver by Workforce name", () => {
  const rows = [row(1, { mapping_status: "MATCHED", workforce_display_name: "Alessandro Facchetti" }), row(2)];
  assert.equal(filterQualityDrivers(rows, "all", "alessandro").length, 1);
});

test("search finds driver by Transporter ID", () => {
  const rows = [row(1, { transporter_external_id: "A13-UNIQUE" }), row(2)];
  assert.equal(filterQualityDrivers(rows, "all", "13-unique")[0].row_index, 1);
});

test("matched filter is exact", () => {
  const rows = [row(1, { mapping_status: "MATCHED" }), row(2), row(3, { mapping_status: "AMBIGUOUS" })];
  assert.deepEqual(filterQualityDrivers(rows, "matched").map(item => item.row_index), [1]);
});

test("unmapped filter is exact", () => {
  const rows = [row(1, { mapping_status: "MATCHED" }), row(2), row(3, { mapping_status: "AMBIGUOUS" })];
  assert.deepEqual(filterQualityDrivers(rows, "unmapped").map(item => item.row_index), [2]);
});

test("ambiguous filter is exact", () => {
  const rows = [row(1, { mapping_status: "MATCHED" }), row(2), row(3, { mapping_status: "AMBIGUOUS" })];
  assert.deepEqual(filterQualityDrivers(rows, "ambiguous").map(item => item.row_index), [3]);
});

test("DCR sort uses normalized numeric values", () => {
  const low = row(1);
  const high = row(2);
  low.metrics.find(item => item.metric_key === "delivery_completion_rate").current.numeric_value = 80;
  high.metrics.find(item => item.metric_key === "delivery_completion_rate").current.numeric_value = 99;
  assert.deepEqual(sortQualityDrivers([high, low], { key: "delivery_completion_rate", direction: "asc" }).map(item => item.row_index), [1, 2]);
});

test("POD sort supports descending order", () => {
  const low = row(1);
  const high = row(2);
  low.metrics.find(item => item.metric_key === "photo_on_delivery").current.numeric_value = 80;
  high.metrics.find(item => item.metric_key === "photo_on_delivery").current.numeric_value = 99;
  assert.deepEqual(sortQualityDrivers([low, high], { key: "photo_on_delivery", direction: "desc" }).map(item => item.row_index), [2, 1]);
});

test("default sort preserves stable import row order", () => {
  assert.deepEqual(sortQualityDrivers([row(3), row(1), row(2)], { key: "row_index", direction: "asc" }).map(item => item.row_index), [1, 2, 3]);
});

test("detail panel opens inline and shows all eight metrics including LoR", () => {
  const html = markup([row(1)], { selectedRowId: "row-1" });
  assert.match(html, /dsp-quality-driver-detail/);
  assert.equal((html.match(/dsp-quality-driver-detail-metric"/g) || []).length, 8);
  assert.match(html, /LoR DPMO/);
});

test("matched detail exposes canonical Workforce CTA", () => {
  const html = markup([row(7, { mapping_status: "MATCHED", workforce_member_id: 42 })], { selectedRowId: "row-7" });
  assert.match(html, /data-quality-driver-workforce="42"/);
  assert.match(html, /Apri driver Workforce/);
});

test("unmapped detail has no fake Workforce CTA", () => {
  const html = markup([row(1)], { selectedRowId: "row-1" });
  assert.doesNotMatch(html, /Apri driver Workforce|Associa a Workforce/);
});

test("detail renders previous value delta and semantic direction", () => {
  const html = markup([row(1)], { selectedRowId: "row-1" });
  assert.match(html, /Precedente/);
  assert.match(html, /Delta/);
  assert.match(html, /Migliorata|Peggiorata|Confronto non disponibile/);
});

test("driver without previous comparison has approved neutral message", () => {
  const withoutPrevious = row(1);
  withoutPrevious.metrics = withoutPrevious.metrics.map(item => ({
    ...item,
    previous: { available: false, value_state: "MISSING" },
    delta: { numeric_delta: null, direction_adjusted_improvement: "unknown" },
  }));
  assert.match(markup([withoutPrevious], { selectedRowId: "row-1" }), /Nessun confronto precedente disponibile\./);
});

test("summary is limited to three primary KPIs with conditional ambiguous signal", () => {
  const html = markup([row(1, { mapping_status: "MATCHED" }), row(2), row(3, { mapping_status: "AMBIGUOUS" })]);
  assert.match(html, /Transporter totali[\s\S]*Associati[\s\S]*Da associare/);
  assert.match(html, /Associazioni ambigue/);
  assert.doesNotMatch(html, /Overall Score|Ranking/);
});

test("filter without results is an empty state and not an error", () => {
  const html = qualityDriversMarkup({ phase: "available", data: data([row(1)]), filter: "matched", search: "", sort: { key: "row_index", direction: "asc" } });
  assert.match(html, /Nessun driver corrisponde ai filtri selezionati/);
  assert.doesNotMatch(html, /role="alert"/);
});

test("scorecard without transporter rows has semantic empty state", () => {
  assert.match(markup([]), /Nessuna performance driver disponibile/);
});

test("drivers endpoint client is read-only GET", async () => {
  let request;
  const result = await getLatestQualityDrivers({ fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => data() };
  } });
  assert.equal(request.url, "/api/dsp-quality/scorecards/latest/drivers");
  assert.equal(request.options.method, "GET");
  assert.equal(result.summary.total, 1);
});

test("drivers endpoint is lazy and requested only on Driver tab", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /section === "drivers"[\s\S]*loadDrivers/);
  assert.match(controller, /getQualityDrivers/);
  assert.doesNotMatch(controller, /loadLatest[\s\S]{0,120}getQualityDrivers/);
});

test("cache busting reaches the DSP shell and Q7 Driver module", async () => {
  const [loader, shell, controller, presenter] = await Promise.all([
    source("assets/js/modules/workspace-loader.js"),
    source("assets/js/modules/dsp-shell/index.js"),
    source("assets/js/modules/dsp-quality/index.js"),
    source("assets/js/modules/dsp-quality/presenter.js"),
  ]);
  assert.match(loader, /dsp-shell\/index\.js\?v=19/);
  assert.match(shell, /dsp-quality\/index\.js\?v=20/);
  assert.match(controller, /presenter\.js\?v=15/);
  assert.match(presenter, /drivers-presenter\.js\?v=7/);
});

test("Driver UI has accessible sort row and mapping semantics", () => {
  const html = markup();
  assert.match(html, /aria-sort="none"/);
  assert.match(html, /aria-label="Ordina per DCR"/);
  assert.match(html, /<th scope="row">/);
  assert.match(html, /Da associare/);
});

test("mobile 390 switches table rows to cards without fixed viewport width", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-driver-table tbody tr[\s\S]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(css, /dsp-quality-driver-detail-grid \{ grid-template-columns: 1fr/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});

test("Panoramica Q5 remains persisted and Metriche Q6 remains wired", async () => {
  const presenter = await source("assets/js/modules/dsp-quality/presenter.js");
  assert.match(presenter, /persistedOverview\(view\.latest\)/);
  assert.match(presenter, /qualityMetricsMarkup\(view\.metrics\)/);
});

test("drivers presentation stays in a dedicated non-monolithic module", async () => {
  const [presenter, drivers] = await Promise.all([
    source("assets/js/modules/dsp-quality/presenter.js"),
    source("assets/js/modules/dsp-quality/drivers-presenter.js"),
  ]);
  assert.match(presenter, /drivers-presenter\.js/);
  assert.match(drivers, /filterQualityDrivers/);
  assert.match(drivers, /sortQualityDrivers/);
});

test("controller supports filters search sort detail retry and Workforce navigation", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  for (const token of ["data-quality-drivers-filter", "data-quality-drivers-search", "data-quality-drivers-sort", "data-quality-driver-open", "data-quality-drivers-retry", "data-quality-driver-workforce"]) {
    assert.match(controller, new RegExp(token));
  }
  assert.match(controller, /view: "workforce", driverId: workforceId/);
});

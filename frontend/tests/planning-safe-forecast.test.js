import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { sourceLabel } from "../assets/js/modules/planning-operations/forecast-editor.js";
import { renderForecast } from "../assets/js/modules/planning-operations/forecast.js";


const rejectedCoverage = {
  available: true,
  items: [
    {
      cycle: "NEXT_DAY", segment: null, forecast: null, raw_forecast: 239,
      requirement: null, assigned: 45, requirement_gap: null, reserve: null,
      status: "NO_FORECAST", source: "LEGACY_IMPORT_BACKFILL",
      authority_status: "REJECTED_TEMPLATE",
      detection_reason: "LONG_ARITHMETIC_SEQUENCE",
    },
    {
      cycle: "SAME_DAY", segment: "A", forecast: 20, requirement: 22,
      assigned: 15, requirement_gap: 7, reserve: 0, status: "UNDER_FORECAST",
      source: "LEGACY_IMPORT_BACKFILL", authority_status: "SUSPECT_TEMPLATE",
    },
    {
      cycle: "SAME_DAY", segment: "B_C", forecast: 18, requirement: 20,
      assigned: 16, requirement_gap: 4, reserve: 0, status: "UNDER_FORECAST",
      source: "LEGACY_IMPORT_BACKFILL", authority_status: "SUSPECT_TEMPLATE",
    },
  ],
};


test("forecast rejected non mostra il valore raw nel KPI", () => {
  const html = renderForecast(rejectedCoverage, { writable: true });
  assert.doesNotMatch(html, />239</);
  assert.match(html, /Forecast Next Day da impostare/);
});


test("forecast rejected propone Inserisci fabbisogno", () => {
  assert.match(
    renderForecast(rejectedCoverage, { writable: true }),
    /data-open-planning-forecast>Inserisci fabbisogno/,
  );
});


test("manual override viene visualizzato come effective", () => {
  const manual = structuredClone(rejectedCoverage);
  manual.items[0] = {
    ...manual.items[0], forecast: 70, requirement: 77, raw_forecast: 70,
    status: "UNDER_FORECAST", source: "MANUAL_PLANNING_INPUT",
    authority_status: "AUTHORITATIVE",
  };
  const html = renderForecast(manual, { writable: true });
  assert.match(html, />70</);
  assert.match(html, /Fonte: Inserimento manuale/);
  assert.doesNotMatch(html, /dato presente nel file/i);
});


test("source label distingue manuale, sospetto e scartato", () => {
  assert.equal(sourceLabel("MANUAL_PLANNING_INPUT"), "Inserimento manuale");
  assert.equal(sourceLabel("IMPORT", "SUSPECT_TEMPLATE"), "Dato importato sospetto");
  assert.equal(sourceLabel("IMPORT", "REJECTED_TEMPLATE"), "Dato importato scartato");
});


test("warning rejected usa il testo operativo richiesto", () => {
  const html = renderForecast(rejectedCoverage);
  assert.match(
    html,
    /Il valore presente nel file non è stato considerato operativo\./,
  );
});


test("Same Day sospetto resta visibile con warning di fonte", () => {
  const html = renderForecast(rejectedCoverage);
  assert.match(html, />20</);
  assert.match(html, />18</);
  assert.equal((html.match(/Dato importato sospetto/g) || []).length, 2);
});


test("Planning usa i campi effective condivisi e non raw_forecast", () => {
  const html = renderForecast(rejectedCoverage);
  assert.match(html, /Forecast assente/);
  assert.doesNotMatch(html, /raw_forecast/);
});


test("bridge Workforce e DSP propagano authority e valore effective", async () => {
  const planningBridge = await readFile(
    new URL("../../backend/app/api/planning_workforce_bridge.py", import.meta.url),
    "utf8",
  );
  const dspBridge = await readFile(
    new URL("../../backend/app/plugins/dsp_workspace/application/workforce_read_bridge.py", import.meta.url),
    "utf8",
  );
  assert.match(planningBridge, /coverage_projection\(coverage_response\)/);
  assert.match(dspBridge, /forecast=item\.forecast_routes/);
  assert.match(dspBridge, /authority_status=/);
  assert.match(dspBridge, /FORECAST_TEMPLATE_REJECTED/);
});


test("layout rejected resta responsive a 390 px senza overflow fisso", async () => {
  const css = await readFile(
    new URL("../assets/css/planning-workspace.css", import.meta.url),
    "utf8",
  );
  assert.match(css, /@media\s*\(max-width:\s*640px\)/);
  assert.match(css, /planning-coverage-buckets\s*\{\s*grid-template-columns:\s*1fr/);
  assert.doesNotMatch(css, /planning-forecast-template-warning[^}]*width:\s*\d{3,}px/s);
});

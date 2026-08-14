import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  changedRequirements,
  forecastDraft,
  renderForecastEditor,
  requirementPreview,
  sourceLabel,
} from "../assets/js/modules/planning-operations/forecast-editor.js";
import { renderForecast } from "../assets/js/modules/planning-operations/forecast.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

const coverage = {
  available: true,
  fingerprint: "a".repeat(64),
  items: [
    {
      cycle: "NEXT_DAY", segment: null, forecast: 240, requirement: 264,
      assigned: 80, requirement_gap: 184, reserve: 0, status: "UNDER_FORECAST",
      source: "IMPORT",
    },
    {
      cycle: "SAME_DAY", segment: "A", forecast: 20, requirement: 22,
      assigned: 10, requirement_gap: 12, reserve: 0, status: "UNDER_FORECAST",
      source: "LEGACY_IMPORT_BACKFILL",
    },
    {
      cycle: "SAME_DAY", segment: "B_C", forecast: 18, requirement: 20,
      assigned: 9, requirement_gap: 11, reserve: 0, status: "UNDER_FORECAST",
      source: "MANUAL_PLANNING_INPUT",
    },
  ],
};


test("Planning espone la CTA Modifica fabbisogno solo in scrittura", () => {
  assert.match(renderForecast(coverage, { writable: true }), /Modifica fabbisogno/);
  assert.doesNotMatch(renderForecast(coverage, { writable: false }), /Modifica fabbisogno/);
});


test("editor mostra giorno selezionato, tre input e valori precompilati", () => {
  const draft = forecastDraft(coverage);
  const html = renderForecastEditor({
    operationLabel: "sabato 15 agosto",
    coverage,
    editor: { open: true, saving: false, error: null, draft, initial: { ...draft } },
  });
  assert.match(html, /sabato 15 agosto/);
  assert.equal((html.match(/data-manual-coverage-input=/g) || []).length, 3);
  assert.match(html, /value="240"/);
  assert.match(html, /value="20"/);
  assert.match(html, /value="18"/);
});


test("preview requirement applica il 10% con arrotondamento half-up", () => {
  assert.equal(requirementPreview("76"), 84);
  assert.equal(requirementPreview("78"), 86);
  assert.equal(requirementPreview("20"), 22);
  assert.equal(requirementPreview("18"), 20);
  assert.equal(requirementPreview("0"), 0);
  assert.equal(requirementPreview(""), null);
});


test("source label distingue import, manuale e nessun dato", () => {
  assert.equal(sourceLabel("IMPORT"), "Planning Amazon importato");
  assert.equal(sourceLabel("LEGACY_IMPORT_BACKFILL"), "Planning Amazon importato");
  assert.equal(sourceLabel("MANUAL_PLANNING_INPUT"), "Inserimento manuale");
  assert.equal(sourceLabel(null), "Nessun dato");
});


test("partial edit invia soltanto il bucket cambiato", () => {
  const initial = forecastDraft(coverage);
  const editor = {
    initial,
    draft: { ...initial, NEXT_DAY: "76" },
  };
  assert.deepEqual(changedRequirements(editor), {
    requirements: [{ cycle: "NEXT_DAY", segment: null, forecast_routes: 76 }],
    clearedExisting: false,
  });
});


test("zero resta un valore reale e non equivale a campo vuoto", () => {
  const changed = changedRequirements({
    initial: { NEXT_DAY: "", SAME_DAY_A: "", SAME_DAY_B_C: "" },
    draft: { NEXT_DAY: "0", SAME_DAY_A: "", SAME_DAY_B_C: "" },
  });
  assert.equal(changed.requirements[0].forecast_routes, 0);
});


test("campo svuotato non viene interpretato come cancellazione implicita", () => {
  const changed = changedRequirements({
    initial: { NEXT_DAY: "76", SAME_DAY_A: "20", SAME_DAY_B_C: "18" },
    draft: { NEXT_DAY: "", SAME_DAY_A: "20", SAME_DAY_B_C: "18" },
  });
  assert.equal(changed.clearedExisting, true);
  assert.deepEqual(changed.requirements, []);
});


test("editor rende loading ed errore senza perdere i valori", () => {
  const draft = forecastDraft(coverage);
  const loading = renderForecastEditor({
    operationLabel: "sabato 15 agosto", coverage,
    editor: { open: true, saving: true, error: null, draft, initial: draft },
  });
  const failed = renderForecastEditor({
    operationLabel: "sabato 15 agosto", coverage,
    editor: { open: true, saving: false, error: "Errore controllato", draft, initial: draft },
  });
  assert.match(loading, /Salvataggio…/);
  assert.match(loading, /disabled/);
  assert.match(failed, /role="alert"/);
  assert.match(failed, /Errore controllato/);
});


test("API usa PUT sul giorno e non accetta organization client-controlled", async () => {
  const api = await source("assets/js/api.js");
  assert.match(api, /saveManualPlanningCoverage\(operationDate, payload\)/);
  assert.match(api, /planning\/coverage\/\$\{encodeURIComponent\(operationDate\)\}/);
  assert.match(api, /method: "PUT"/);
  assert.doesNotMatch(api, /saveManualPlanningCoverage[\s\S]{0,500}organization_id/);
});


test("controller usa fingerprint, gestisce 409 e ricarica Planning senza reload", async () => {
  const controller = await source("assets/js/modules/planning-operations/index.js");
  assert.match(controller, /expected_fingerprint: state\.payload\.coverage\.fingerprint/);
  assert.match(controller, /error\?\.status === 409/);
  assert.match(controller, /Il fabbisogno è cambiato/);
  assert.match(controller, /await load\(state\.selectedOperationalDate\)/);
  assert.doesNotMatch(controller, /location\.reload/);
});


test("cambio giorno chiude l'editor e mantiene scope day-first", async () => {
  const controller = await source("assets/js/modules/planning-operations/index.js");
  assert.match(controller, /async function selectOperationalDate[\s\S]*resetForecastEditor\(\)/);
  assert.match(controller, /saveForecast\(state\.selectedOperationalDate/);
});


test("Coverage Planning conserva source e fingerprint condivisi", async () => {
  const bridge = await source("../backend/app/api/planning_workforce_bridge.py");
  const projection = await source("../backend/app/plugins/dsp_workspace/application/workforce_read_bridge.py");
  assert.match(bridge, /"fingerprint": coverage_response\.fingerprint/);
  assert.match(projection, /source=item\.source/);
  assert.match(projection, /source_reference=item\.source_reference/);
});


test("layout mobile 390 resta verticale, touch-friendly e senza larghezze rigide", async () => {
  const css = await source("assets/css/planning-workspace.css");
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.planning-forecast-fields > label \{ grid-template-columns: 1fr/);
  assert.match(css, /\.planning-forecast-editor > footer button \{ width: 100%/);
  assert.match(css, /\.planning-forecast-editor > footer button \{ min-height: 44px/);
  assert.doesNotMatch(css, /\.planning-forecast-editor[^}]*width:\s*[7-9]\d\dpx/);
});

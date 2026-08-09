import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  importQualityScorecard,
  previewQualityScorecard,
} from "../assets/js/modules/dsp-quality/api.js";
import {
  formatQualityFileSize,
  qualityActionLabel,
  qualityErrorMessage,
  validateQualityFile,
} from "../assets/js/modules/dsp-quality/import.js";
import {
  qualityEmptyMarkup,
  qualityPreviewMarkup,
  qualitySuccessMarkup,
} from "../assets/js/modules/dsp-quality/presenter.js";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "../assets/js/modules/dsp-quality/state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function pdfFile(name = "scorecard.pdf", size = 2048, type = "application/pdf") {
  const blob = new Blob([new Uint8Array(size)], { type });
  Object.defineProperty(blob, "name", { value: name });
  return blob;
}


function preview(action = "CREATE", overrides = {}) {
  return {
    valid: true,
    preview_token: "preview-token-123456789",
    identity: {
      dsp_identifier: "DSP-DEMO",
      station: "ST01",
      reported_week: 47,
      reported_year: 2025,
      overall_score: "45.41",
      overall_standing: "Poor",
      rank: 4,
    },
    counts: {
      dsp_metrics_count: 18,
      transporter_rows_count: 159,
      focus_areas_count: 3,
      standards_count: 13,
      working_hours_exception_count: 0,
    },
    validation: { errors: [], warnings: [], infos: [] },
    mapping: { matched_transporters: 8, unmapped_transporters: 150, ambiguous_transporters: 1 },
    idempotency: { action },
    ...overrides,
  };
}


function previewView(overrides = {}) {
  const file = pdfFile();
  const state = {
    ...createDspQualityState({ canImport: true }),
    phase: "preview-ready",
    file,
    preview: preview(),
    ...overrides,
  };
  return deriveDspQualityView(state);
}


test("DSP primary navigation order remains Home Planning Workforce DSP Fleet Learn", async () => {
  const html = await source("index.html");
  const nav = html.match(/<nav class="workspace-tabs"[\s\S]*?<\/nav>/)?.[0] || "";
  const labels = [...nav.matchAll(/data-workspace-view="[^"]+"[\s\S]*?>\s*([^<]+)\s*<\/button>/g)].map(match => match[1].trim());
  assert.deepEqual(labels, ["Home", "Planning", "Workforce", "DSP", "Fleet", "Learn"]);
});

test("DSP shell exposes Operatività and Qualità as accessible tabs", async () => {
  const html = await source("index.html");
  assert.match(html, /role="tablist" aria-label="Aree DSP"/);
  assert.match(html, /data-dsp-area="operations"[\s\S]*Operatività/);
  assert.match(html, /data-dsp-area="quality"[\s\S]*Qualità/);
});

test("Operatività is the default DSP area", async () => {
  const html = await source("index.html");
  assert.match(html, /id="dspOperationsTab"[\s\S]*aria-selected="true"/);
  assert.match(html, /id="dspQualityPanel"[\s\S]*hidden/);
});

test("DSP area switch is SPA-based and never changes location", async () => {
  const shell = await source("assets/js/modules/dsp-shell/index.js");
  assert.match(shell, /nodes\.operations\.hidden/);
  assert.match(shell, /nodes\.quality\.hidden/);
  assert.doesNotMatch(shell, /location\.|window\.open|href\s*=/);
});

test("DSP Operations keeps its existing isolated controller", async () => {
  const shell = await source("assets/js/modules/dsp-shell/index.js");
  assert.match(shell, /initDspWorkspace/);
  assert.match(shell, /prepareDspFirstPaint/);
  assert.doesNotMatch(shell, /date-changed|filter-changed|search-changed/);
});

test("Quality empty state uses approved product copy", () => {
  const markup = qualityEmptyMarkup(true);
  assert.match(markup, /Qualità settimanale/);
  assert.match(markup, /Scorecard Amazon/);
  assert.match(markup, /Importa la scorecard settimanale/);
});

test("writer sees Importa scorecard CTA", () => {
  assert.match(qualityEmptyMarkup(true), /data-quality-pick>Importa scorecard/);
});

test("read-only user sees Quality but no import CTA", () => {
  const markup = qualityEmptyMarkup(false);
  assert.match(markup, /Consultazione Quality/);
  assert.doesNotMatch(markup, /data-quality-pick/);
});

test("PDF selection accepts a real PDF", () => {
  assert.equal(validateQualityFile(pdfFile()), null);
});

test("non-PDF file is rejected", () => {
  assert.match(validateQualityFile(pdfFile("scorecard.xlsx", 100, "application/vnd.ms-excel")), /Formato non supportato/);
});

test("file above 8 MB is rejected", () => {
  assert.match(validateQualityFile(pdfFile("large.pdf", 8 * 1024 * 1024 + 1)), /8 MB/);
});

test("file size is presented readably", () => {
  assert.equal(formatQualityFileSize(2 * 1024 * 1024), "2.0 MB");
});

test("preview client sends multipart PDF to the Q3 preview endpoint", async () => {
  let request;
  const file = pdfFile();
  await previewQualityScorecard(file, { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => preview() };
  } });
  assert.equal(request.url, "/api/dsp-quality/scorecards/preview");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.body.get("file").size, file.size);
  assert.equal(request.options.body.get("file").type, file.type);
});

test("loading state preserves selected filename", () => {
  const state = applyDspQualityEvent(createDspQualityState({ canImport: true }), {
    type: "preview-started", file: pdfFile("weekly.pdf"),
  });
  assert.equal(state.phase, "preview-loading");
  assert.equal(state.file.name, "weekly.pdf");
});

test("preview renders identity from the API response", () => {
  const markup = qualityPreviewMarkup(previewView());
  assert.match(markup, /DSP-DEMO/);
  assert.match(markup, /ST01/);
  assert.match(markup, /Week 47 \/ 2025/);
  assert.match(markup, /45\.41/);
  assert.match(markup, /Poor/);
  assert.match(markup, /Rank[\s\S]*4/);
});

test("preview renders all Q3 counts", () => {
  const markup = qualityPreviewMarkup(previewView());
  for (const label of ["Metriche DSP", "Transporter", "Focus area", "Standard", "Eccezioni WH"]) {
    assert.match(markup, new RegExp(label));
  }
  assert.match(markup, /Transporter<\/dt><dd>159/);
});

test("validation messages include textual severity", () => {
  const view = previewView({ preview: preview("CREATE", {
    validation: {
      errors: [{ code: "BAD", message: "Campo obbligatorio assente" }],
      warnings: [{ code: "WARN", message: "Driver non associato" }],
      infos: [{ code: "INFO", message: "Template riconosciuto" }],
    },
  }) });
  const markup = qualityPreviewMarkup(view);
  assert.match(markup, />ERROR /);
  assert.match(markup, />WARNING /);
  assert.match(markup, />INFO /);
});

test("validation errors block confirmation", () => {
  const view = previewView({ preview: preview("CREATE", {
    valid: false,
    validation: { errors: [{ code: "BAD", message: "Errore" }], warnings: [], infos: [] },
  }) });
  assert.equal(view.canConfirm, false);
  assert.match(qualityPreviewMarkup(view), /data-quality-confirm disabled/);
});

test("validation warnings do not block confirmation", () => {
  const view = previewView({ preview: preview("CREATE", {
    validation: { errors: [], warnings: [{ code: "WARN", message: "Verifica" }], infos: [] },
  }) });
  assert.equal(view.canConfirm, true);
});

test("mapping summary shows only matched unmapped and ambiguous counts", () => {
  const markup = qualityPreviewMarkup(previewView());
  assert.match(markup, /Associati[\s\S]*8/);
  assert.match(markup, /Non associati[\s\S]*150/);
  assert.match(markup, /Ambigui[\s\S]*1/);
  assert.doesNotMatch(markup, /transporter_external_id/);
});

test("CREATE idempotency copy is backend-action driven", () => {
  assert.equal(qualityActionLabel("CREATE"), "Nuova scorecard");
});

test("NO_OP idempotency copy is backend-action driven", () => {
  assert.equal(qualityActionLabel("NO_OP"), "Questa scorecard è già stata importata.");
});

test("NEW_REVISION idempotency copy is backend-action driven", () => {
  assert.match(qualityActionLabel("NEW_REVISION"), /nuova revisione/);
});

test("confirm client submits preview token and expected action", async () => {
  let form;
  const file = pdfFile();
  await importQualityScorecard({
    file, previewToken: "preview-token-123456789", expectedAction: "CREATE",
  }, { fetcher: async (url, options) => {
    assert.equal(url, "/api/dsp-quality/scorecards/import");
    form = options.body;
    return { ok: true, json: async () => ({ action: "CREATE" }) };
  } });
  assert.equal(form.get("file").size, file.size);
  assert.equal(form.get("file").type, file.type);
  assert.equal(form.get("preview_token"), "preview-token-123456789");
  assert.equal(form.get("expected_action"), "CREATE");
});

test("success view exposes imported scorecard and CTA", () => {
  const view = previewView({
    phase: "success",
    result: { transporter_rows: 159 },
  });
  const markup = qualitySuccessMarkup(view);
  assert.match(markup, /Scorecard importata/);
  assert.match(markup, /Visualizza scorecard/);
  assert.match(markup, /Transporter<\/dt><dd>159/);
});

test("post-import shell contains only Panoramica Metriche and Driver", () => {
  const markup = qualitySuccessMarkup({
    ...previewView({ phase: "success", result: { transporter_rows: 159 } }),
    overviewVisible: true,
    section: "overview",
  });
  assert.match(markup, /Panoramica/);
  assert.match(markup, /Metriche/);
  assert.match(markup, /Driver/);
  assert.doesNotMatch(markup, /Trend|Grafici|Classifica/);
});

test("expired preview token has a clear safe error", () => {
  assert.match(qualityErrorMessage({ status: 409 }, "import"), /preview non è più valida/);
});

test("API failures never expose raw backend details", () => {
  assert.equal(qualityErrorMessage({ status: 500, detail: "stack trace secret" }, "preview"), "Analisi non riuscita. Controlla il file e riprova.");
});

test("Quality values are never hardcoded in production frontend", async () => {
  const files = await Promise.all([
    "assets/js/modules/dsp-quality/api.js",
    "assets/js/modules/dsp-quality/state.js",
    "assets/js/modules/dsp-quality/import.js",
    "assets/js/modules/dsp-quality/presenter.js",
    "assets/js/modules/dsp-quality/index.js",
  ].map(source));
  const code = files.join("\n");
  assert.doesNotMatch(code, /PROF|DLO2|45\.41|\b159\b/);
});

test("DSP shell supports keyboard tab navigation", async () => {
  const shell = await source("assets/js/modules/dsp-shell/index.js");
  for (const key of ["ArrowRight", "ArrowLeft", "Home", "End"]) assert.match(shell, new RegExp(key));
  assert.match(shell, /tab\.focus\(\)/);
});

test("Quality file input remains accessible without drag and drop", () => {
  const markup = qualityEmptyMarkup(true);
  assert.match(markup, /type="file"/);
  assert.match(markup, /aria-label="Seleziona scorecard Amazon PDF"/);
  assert.match(markup, /data-quality-pick/);
});

test("tablet layout uses a two-column summary", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 820px\)[\s\S]*grid-template-columns: repeat\(2/);
});

test("mobile layout becomes vertical without fixed widths", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /width: 100%/);
  assert.doesNotMatch(css, /min-width:\s*[4-9]\d{2}px/);
});

test("workspace loader mounts the DSP shell and dedicated Quality stylesheet", async () => {
  const loader = await source("assets/js/modules/workspace-loader.js");
  assert.match(loader, /dsp-shell\/index\.js/);
  assert.match(loader, /dsp-quality\.css/);
});

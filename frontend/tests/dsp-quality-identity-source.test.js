import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyExactTransporterIdentitySource,
  previewTransporterIdentitySource,
} from "../assets/js/modules/dsp-quality/api.js";
import {
  applyIdentitySourceEvent,
  createIdentitySourceState,
  identityRowsForBucket,
  validateIdentitySourceFile,
} from "../assets/js/modules/dsp-quality/identity-source.js";
import { identitySourceMarkup } from "../assets/js/modules/dsp-quality/identity-source-presenter.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const upload = name => {
  const blob = new Blob(["identity-source"], { type: "application/octet-stream" });
  Object.defineProperty(blob, "name", { value: name });
  return blob;
};


const preview = {
  valid: true,
  schema_status: "READY",
  scorecard_id: "week-45",
  preview_token: "signed-preview-token",
  default_bucket: "suggested",
  source: {
    filename: "Planning.xlsx",
    sheet: "Planning",
    transporter_column: "T-ID",
    driver_column: "drivers",
    rows_detected: 146,
  },
  coverage: {
    quality_transporters: 146,
    source_transporters: 142,
    exact_matches: 2,
    suggestions: 120,
    unresolved: 20,
    conflicts: 4,
    already_verified: 3,
  },
  rows: [
    { transporter_external_id: "A-EXACT", source_driver_value: "WF-1", proposed_workforce_member_id: 1, proposed_display_name: "Mario Rossi", status: "EXACT", reason: "Canonico" },
    { transporter_external_id: "A-SUGGEST", source_driver_value: "Giulia Bianchi", proposed_workforce_member_id: 2, proposed_display_name: "Giulia Bianchi", status: "SUGGESTED", reason: "Verifica" },
    { transporter_external_id: "A-MISSING", source_driver_value: "Nessuno", status: "UNRESOLVED", reason: "Non trovato" },
    { transporter_external_id: "A-CONFLICT", source_driver_value: "Omonimo", status: "CONFLICT", reason: "Ambiguo" },
    { transporter_external_id: "A-VERIFIED", source_driver_value: "Altro", status: "CONFLICT_WITH_VERIFIED_MAPPING", reason: "Mapping verificato" },
  ],
};


const availableState = (overrides = {}) => ({
  ...createIdentitySourceState(),
  phase: "available",
  preview,
  bucket: "suggested",
  ...overrides,
});


test("Riconcilia da una fonte is visible as recommended optional method", () => {
  const html = identitySourceMarkup(createIdentitySourceState());
  assert.match(html, /Riconcilia da una fonte/);
  assert.match(html, /Metodo consigliato/);
});


test("optional copy explains that uncertain matches stay manual", () => {
  const html = identitySourceMarkup(createIdentitySourceState());
  assert.match(html, /Le associazioni non certe resteranno da verificare manualmente/);
});


test("xlsx upload is accepted by client validation", () => {
  assert.equal(validateIdentitySourceFile({ name: "drivers.xlsx" }), null);
});


test("csv upload is accepted by client validation", () => {
  assert.equal(validateIdentitySourceFile({ name: "drivers.csv" }), null);
  assert.match(validateIdentitySourceFile({ name: "drivers.pdf" }), /xlsx.*csv/);
});


test("detected sheet is rendered", () => {
  assert.match(identitySourceMarkup(availableState()), /Foglio[\s\S]*Planning/);
});


test("detected semantic columns are rendered", () => {
  const html = identitySourceMarkup(availableState());
  assert.match(html, /Transporter column[\s\S]*T-ID/);
  assert.match(html, /Driver column[\s\S]*drivers/);
});


test("coverage counts are dynamic", () => {
  const html = identitySourceMarkup(availableState());
  for (const value of [146, 120, 20, 4]) assert.match(html, new RegExp(`>${value}<`));
});


test("exact bucket contains exact evidence", () => {
  assert.deepEqual(identityRowsForBucket(preview.rows, "exact").map(row => row.transporter_external_id), ["A-EXACT"]);
});


test("suggestions bucket contains only reviewable evidence", () => {
  assert.deepEqual(identityRowsForBucket(preview.rows, "suggested").map(row => row.transporter_external_id), ["A-SUGGEST"]);
});


test("unresolved bucket contains missing identities", () => {
  assert.deepEqual(identityRowsForBucket(preview.rows, "unresolved").map(row => row.transporter_external_id), ["A-MISSING"]);
});


test("conflict bucket includes verified mapping conflicts", () => {
  assert.deepEqual(identityRowsForBucket(preview.rows, "conflict").map(row => row.transporter_external_id), ["A-CONFLICT", "A-VERIFIED"]);
});


test("exact apply is explicit and includes the exact count", () => {
  assert.match(identitySourceMarkup(availableState({ bucket: "exact" })), /Applica 2 associazioni certe/);
});


test("no silent or automatic apply copy exists", () => {
  const html = identitySourceMarkup(availableState());
  assert.doesNotMatch(html, /applica automaticamente|conferma tutti/i);
});


test("suggestion requires an individual confirmation", () => {
  const html = identitySourceMarkup(availableState());
  assert.match(html, /data-quality-source-confirm="A-SUGGEST"/);
  assert.match(html, />Conferma</);
});


test("suggestion offers choose another driver", () => {
  assert.match(identitySourceMarkup(availableState()), /data-quality-source-choose="A-SUGGEST"[\s\S]*Scegli altro/);
});


test("verified mapping conflicts have a textual status", () => {
  const html = identitySourceMarkup(availableState({ bucket: "conflict" }));
  assert.match(html, /CONFLICT_WITH_VERIFIED_MAPPING/);
  assert.match(html, /Mapping verificato/);
});


test("manual fallback remains visible without a file", () => {
  assert.match(identitySourceMarkup(createIdentitySourceState()), /Non hai un file\?[\s\S]*Associa manualmente/);
});


test("preview API sends the selected scorecard and xlsx file", async () => {
  let request;
  await previewTransporterIdentitySource({ file: upload("drivers.xlsx"), scorecardId: "week-45" }, { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => preview };
  } });
  assert.equal(request.url, "/api/dsp-quality/transporter-mappings/source-preview");
  assert.equal(request.options.body.get("scorecard_id"), "week-45");
  assert.equal(request.options.body.get("file").size, "identity-source".length);
});


test("exact apply API resends source and signed token", async () => {
  let request;
  await applyExactTransporterIdentitySource({ file: upload("drivers.csv"), scorecardId: "week-45", previewToken: "signed-preview-token" }, { fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ applied: 2 }) };
  } });
  assert.equal(request.url, "/api/dsp-quality/transporter-mappings/source-apply-exact");
  assert.equal(request.options.body.get("preview_token"), "signed-preview-token");
});


test("source apply refreshes Q8 reconciliation summary", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /applyExactIdentitySource[\s\S]*loadReconciliation\(\{ keepFilter: true \}\)/);
});


test("source apply refreshes Q7 drivers", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /applyExactIdentitySource[\s\S]*loadDrivers\(\{ force: true \}\)/);
});


test("mapping stays delegated to existing Q8 PUT for history-wide identity", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /confirmIdentitySuggestion[\s\S]*confirmMapping\(\)/);
  assert.match(controller, /putTransporterMapping/);
});


test("sensitive unrelated columns are never rendered", () => {
  const html = identitySourceMarkup(availableState());
  assert.doesNotMatch(html, /codice fiscale|telefono|email|C\.F/i);
});


test("mobile source flow is single-column with 44px controls and no fixed viewport widths", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-source-row[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /dsp-quality-source-row-actions button \{ min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});


test("Q5 Q6 Q7 Q8 Q9 wiring remains intact", async () => {
  const [presenter, controller, reconciliation] = await Promise.all([
    source("assets/js/modules/dsp-quality/presenter.js"),
    source("assets/js/modules/dsp-quality/index.js"),
    source("assets/js/modules/dsp-quality/reconciliation-presenter.js"),
  ]);
  assert.match(presenter, /persistedOverview/);
  assert.match(presenter, /qualityMetricsMarkup/);
  assert.match(presenter, /qualityDriversMarkup/);
  assert.match(controller, /selectedScorecardId/);
  assert.match(reconciliation, /identitySourceMarkup/);
});


test("schema ambiguity state exposes explicit selectors", () => {
  const schema = applyIdentitySourceEvent(createIdentitySourceState(), {
    type: "identity-source-preview-completed",
    preview: {
      valid: false,
      source: {
        candidate_sheets: ["Planning", "Roster"],
        transporter_candidates: ["T-ID"],
        driver_candidates: ["drivers"],
      },
    },
  });
  const html = identitySourceMarkup(schema);
  assert.match(html, /data-quality-identity-selection="sheet"/);
  assert.match(html, /Analizza selezione/);
});

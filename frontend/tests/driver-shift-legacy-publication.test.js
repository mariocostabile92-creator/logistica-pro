import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  renderLegacyPublication,
  renderLegacyPublishSummary,
} from "../assets/js/modules/driver-shift-planning-presenter.js";
import {
  createDriverShiftPlanningState,
  LEGACY_PREVIEW_STATUS,
} from "../assets/js/modules/driver-shift-planning-state.js";
import { shouldRequestLegacyPreview } from "../assets/js/modules/driver-shift-planning.js";


const source = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "", hidden: false });
const planning = { id: 3, status: "DRAFT", version: 2 };
const unavailablePreview = {
  sources: [{ id: 1, status: "UNAVAILABLE_FOR_MERGE" }],
  summary: { ready_to_publish: false, total_source_rows: 0 },
};
const legacyPreview = {
  planning,
  ready_to_publish: true,
  rows_total: 47_800,
  drivers_total: 142,
  period_start: "2025-12-28",
  period_end: "2027-01-03",
  fingerprint: "a".repeat(64),
};


test("unavailable legacy source triggers the dedicated preview", () => {
  assert.equal(shouldRequestLegacyPreview(planning, unavailablePreview), true);
});


test("modern mergeable source never triggers the legacy preview", () => {
  assert.equal(shouldRequestLegacyPreview(planning, {
    sources: [{ status: "AVAILABLE" }],
    summary: { ready_to_publish: true, total_source_rows: 100 },
  }), false);
});


test("mixed modern and unavailable sources stay in normal multi-source flow", () => {
  assert.equal(shouldRequestLegacyPreview(planning, {
    sources: [{ status: "AVAILABLE" }, { status: "UNAVAILABLE_FOR_MERGE" }],
    summary: { ready_to_publish: false, total_source_rows: 100 },
  }), false);
});


test("non-DRAFT planning never requests legacy preview", () => {
  assert.equal(shouldRequestLegacyPreview({ ...planning, status: "ACTIVE" }, unavailablePreview), false);
});


test("legacy loading is explicit and has no stale publish CTA", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.LOADING);
  assert.match(target.innerHTML, /Verifica turni esistenti/);
  assert.doesNotMatch(target.innerHTML, /data-publish-existing-shifts/);
});


test("legacy ready card has the required operational title", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /Turni esistenti rilevati/);
  assert.match(target.innerHTML, /Origine legacy/);
});


test("legacy card renders driver count", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /<dt>Driver<\/dt><dd>142<\/dd>/);
});


test("legacy card renders localized row count", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /47\.800/);
});


test("legacy card renders the full localized period", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /28\/12\/2025/);
  assert.match(target.innerHTML, /03\/01\/2027/);
});


test("legacy limitation copy is honest and non-technical", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /precedente al nuovo sistema multi-file/);
  assert.match(target.innerHTML, /provenienza dettagliata del file originale non/);
  assert.doesNotMatch(target.innerHTML, /workforce_day_statuses|immutable rows|T-ID/);
});


test("primary CTA says Pubblica turni esistenti", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.AVAILABLE, legacyPreview);
  assert.match(target.innerHTML, /data-publish-existing-shifts>Pubblica turni esistenti/);
  assert.doesNotMatch(target.innerHTML, /Legacy publish|Canonical publish/);
});


test("pre-publish dialog is labelled and explains Workforce remains unchanged", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftLegacyPublishDialog"[\s\S]*aria-labelledby="driverShiftLegacyPublishTitle"/);
  assert.match(html, /Stai per pubblicare i turni gi&agrave; presenti/);
  assert.match(html, /Il calendario Workforce non verr&agrave; modificato/);
});


test("dialog summary contains period drivers rows and readable origin", () => {
  const target = element();
  renderLegacyPublishSummary(target, legacyPreview);
  for (const value of ["Periodo", "Driver coinvolti", "Giornate/turni", "Turni esistenti"])
    assert.match(target.innerHTML, new RegExp(value));
});


test("dialog exposes explicit cancel and publish controls", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftLegacyPublishCancel"[^>]*>Annulla/);
  assert.match(html, /id="driverShiftLegacyPublishConfirm"[^>]*>Pubblica/);
});


test("publish payload uses backend version and fingerprint without frontend hashing", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /expected_version: state\.legacyPreview\.planning\?\.version/);
  assert.match(controller, /expected_fingerprint: state\.legacyPreview\.fingerprint/);
  assert.doesNotMatch(controller, /crypto\.subtle|sha256|createHash/);
});


test("success refreshes ACTIVE planning state and notifies Workforce", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /await publishLegacyPlanning[\s\S]*await refresh\(planningId\)/);
  assert.match(controller, /onChanged\(\{ type: "published", planningId, periodStart \}\)/);
});


test("Distribution entry remains the existing ACTIVE planning flow", async () => {
  const [planningController, distributionController, html] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"),
    source("assets/js/modules/driver-shift-distribution.js"),
    source("index.html"),
  ]);
  assert.match(planningController, /distributionController\?\.setPlanning\(state\.planning\)/);
  assert.match(distributionController, /elements\.entry\.hidden = planning\?\.status !== "ACTIVE"/);
  assert.match(html, /id="driverShiftDistributeBtn"[^>]*>Distribuisci turni/);
});


test("409 shows exact stale message refreshes preview and never auto-retries publish", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /I turni sono cambiati dall'ultima verifica\. Aggiorna la preview e riprova\./);
  assert.match(controller, /error\?\.status === 409[\s\S]*await refreshLegacyPreview\(\)/);
  assert.doesNotMatch(controller, /error\?\.status === 409[\s\S]{0,500}publishLegacyPlanning/);
});


test("zero legacy data stays unavailable and has no publish button", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.EMPTY);
  assert.match(target.innerHTML, /non possono essere ricostruiti automaticamente/);
  assert.doesNotMatch(target.innerHTML, /data-publish-existing-shifts/);
});


test("legacy preview error is safe and retryable", () => {
  const target = element();
  renderLegacyPublication(target, LEGACY_PREVIEW_STATUS.ERROR);
  assert.match(target.innerHTML, /Impossibile verificare i turni esistenti/);
  assert.match(target.innerHTML, /data-retry-legacy-preview>Riprova/);
  assert.doesNotMatch(target.innerHTML, /API|422|500/);
});


test("API client exposes only explicit legacy preview and publish endpoints", async () => {
  const api = await source("assets/js/api.js");
  assert.match(api, /getDriverShiftPlanningLegacyPreview[\s\S]*\/legacy-preview/);
  assert.match(api, /publishDriverShiftPlanningLegacy[\s\S]*\/legacy-publish[\s\S]*method: "POST"/);
});


test("state has the five requested statuses preview and publishing flag", () => {
  const store = createDriverShiftPlanningState();
  assert.deepEqual(Object.values(LEGACY_PREVIEW_STATUS), [
    "IDLE", "LOADING", "AVAILABLE", "EMPTY", "ERROR",
  ]);
  assert.equal(store.state.legacyPreviewStatus, "IDLE");
  assert.equal(store.state.legacyPreview, null);
  assert.equal(store.state.legacyPublishing, false);
});


test("mobile 390 layout is single-column with full-width 44px CTA", async () => {
  const css = await source("assets/css/driver-shift-planning.css");
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.match(css, /\.driver-shift-legacy-summary,[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /\.driver-shift-legacy-heading button,[\s\S]*width: 100%/);
  assert.match(css, /\.driver-shift-legacy-heading button,[\s\S]*min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*390px/);
});


test("legacy region is live and dialog restores focus on close", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-planning.js"),
  ]);
  assert.match(html, /id="driverShiftLegacyPublication"[\s\S]*aria-live="polite"/);
  assert.match(controller, /addEventListener\("close", restoreLegacyDialogFocus\)/);
  assert.match(controller, /driverShiftLegacyPublishConfirm"\)\.focus\(\)/);
});

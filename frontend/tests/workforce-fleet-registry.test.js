import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { fleetSyncCounts } from "../assets/js/modules/fleet-sync-view.js";
import {
  workforceStatusLabel,
  workforceSummary,
} from "../assets/js/modules/workforce-view.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


test("Workforce is a primary routed workspace without replacing Operations", async () => {
  const [html, navigation] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/view-navigation.js"),
  ]);
  assert.match(html, /data-workspace-view="workforce"/);
  assert.match(navigation, /workforce: \["workforceSection"\]/);
  assert.match(navigation, /operations: OPERATIONS_SECTIONS/);
  assert.match(html, /id="planningSection"/);
});


test("Workforce page exposes summary period calendar coverage contracts changes import and export", async () => {
  const html = await frontendFile("index.html");
  for (const id of [
    "workforceSummary", "workforceDateFrom", "workforceDateTo",
    "workforceCalendar", "workforceCoverage", "workforceAbsences",
    "workforceContracts", "workforceChanges", "workforceImportForm",
    "workforceExportBtn",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});


test("Workforce summary is deterministic and uses backend availability", () => {
  const summary = workforceSummary(
    [{}, {}],
    [
      { availability: true, status_code: "scheduled" },
      { availability: false, status_code: "sickness" },
    ],
    [{ margin: -1 }],
  );
  assert.deepEqual(summary, {
    members: 2,
    available: 1,
    scheduled: 1,
    absent: 1,
    margin: -1,
  });
  assert.equal(workforceStatusLabel("holiday"), "Ferie");
});


test("Workforce calendar supports day week person and manual audited edits", async () => {
  const [html, page] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
  ]);
  for (const mode of ["day", "week", "person"]) {
    assert.match(html, new RegExp(`data-workforce-view-mode="${mode}"`));
  }
  assert.match(page, /saveWorkforceDayStatus/);
  assert.match(page, /updateWorkforceMember/);
  assert.match(page, /source_reference: "manual"/);
});


test("Workforce import shows recognized sheets and compact matrix", async () => {
  const [view, css] = await Promise.all([
    frontendFile("assets/js/modules/workforce-view.js"),
    frontendFile("assets/css/workforce.css"),
  ]);
  assert.match(view, /Planning turni riconosciuto/);
  assert.match(view, /preview\.sheets\.map/);
  assert.match(view, /preview\.matrix/);
  assert.match(css, /max-height: 540px/);
  assert.match(css, /overflow: auto/);
});


test("Workforce expected disabled state is handled without console noise", async () => {
  const source = await frontendFile("assets/js/modules/workforce-page.js");
  assert.match(source, /isExpectedApiError\(error, \{ statuses: \[404\] \}\)/);
  assert.doesNotMatch(source, /console\.(error|warn|log)/);
  assert.doesNotMatch(source, /fetch\(/);
});


test("Fleet page exposes sync source analysis filters diff and confirmation", async () => {
  const html = await frontendFile("index.html");
  for (const id of [
    "fleetSyncToggle", "fleetSyncFile", "fleetSyncAnalyze",
    "fleetSyncSummary", "fleetSyncFilters", "fleetSyncDiff",
    "fleetSyncConfirm",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /data-fleet-sync-filter="CONFLICT"/);
  assert.match(html, /data-fleet-sync-filter="SENSITIVE"/);
});


test("Fleet sync counters preserve backend action classes", () => {
  assert.deepEqual(fleetSyncCounts([
    { action: "NEW_ASSET", sensitive_fields: [] },
    { action: "UPDATE_EXISTING", sensitive_fields: [{ column: "Sensitive" }] },
    { action: "NO_CHANGE", sensitive_fields: [] },
  ]), {
    NEW_ASSET: 1,
    UPDATE_EXISTING: 1,
    NO_CHANGE: 1,
    sensitive: 1,
  });
});


test("Fleet diff never renders sensitive values and disables ambiguous actions", async () => {
  const source = await frontendFile("assets/js/modules/fleet-sync-view.js");
  assert.match(source, /Campo sensibile rilevato: escluso/);
  assert.match(source, /item\.sensitive_fields\.map\(\(field\)/);
  assert.doesNotMatch(source, /field\.value/);
  assert.match(source, /"CONFLICT", "POSSIBLE_DUPLICATE", "INVALID_ROW"/);
});


test("Fleet selections survive filters and confirmation uses explicit rows", async () => {
  const source = await frontendFile("assets/js/modules/fleet-sync.js");
  assert.match(source, /let selectedRows = new Set\(\)/);
  assert.match(source, /selectedRows\.add\(rowId\)/);
  assert.match(source, /const rowsToApply = \[\.\.\.selectedRows\]/);
  assert.match(source, /confirmFleetSync/);
});


test("recognized workbooks route to their owning module", async () => {
  const [source, preview] = await Promise.all([
    frontendFile("assets/js/modules/import-workbook.js"),
    frontendFile("assets/js/modules/import-preview.js"),
  ]);
  assert.match(source, /data\.recommended_target === "workforce"/);
  assert.match(source, /"fleet:sync-requested"/);
  assert.match(source, /expectedTarget/);
  assert.match(preview, /Riconosciuto e instradato/);
});


test("Workforce and Fleet use only API client calls and sanitized error handling", async () => {
  const sources = await Promise.all([
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/fleet-sync.js"),
    frontendFile("assets/js/modules/fleet-sync-view.js"),
  ]);
  const combined = sources.join("\n");
  assert.doesNotMatch(combined, /fetch\(/);
  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
  assert.match(combined, /userErrorPresentation|isExpectedApiError/);
});


test("new pages cover wide desktop tablet and mobile without fixed canvas widths", async () => {
  const [workforce, fleet] = await Promise.all([
    frontendFile("assets/css/workforce.css"),
    frontendFile("assets/css/fleet-sync.css"),
  ]);
  const css = `${workforce}\n${fleet}`;
  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.doesNotMatch(css, /width:\s*[1-9]\d{3,}px/);
});


test("new controls have labels live regions and keyboard-native controls", async () => {
  const html = await frontendFile("index.html");
  assert.match(html, /id="workforceImportState"[\s\S]*?aria-live="polite"/);
  assert.match(html, /id="fleetSyncState"[\s\S]*?aria-live="polite"/);
  assert.match(html, /aria-label="Vista calendario"/);
  assert.match(html, /aria-label="Filtra proposte"/);
  assert.doesNotMatch(html, /onclick=/);
});


test("API client exposes versioned Workforce and Fleet sync contracts", async () => {
  const source = await frontendFile("assets/js/api.js");
  assert.match(source, /api\/plugins\/workforce\/v1\/import\/preview/);
  assert.match(source, /api\/plugins\/workforce\/v1\/calendar/);
  assert.match(source, /api\/plugins\/fleet\/v1\/sync\/preview/);
  assert.match(source, /api\/plugins\/fleet\/v1\/sync\/confirm/);
});

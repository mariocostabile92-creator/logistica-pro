import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { fleetSyncCounts } from "../assets/js/modules/fleet-sync-view.js";
import {
  workforceCalendarWindow,
  workforceStatusLabel,
  workforceSummary,
} from "../assets/js/modules/workforce-view.js";
import {
  nextWorkforceCellPosition,
  workforceTimeLabel,
} from "../assets/js/modules/workforce-calendar-view.js";
import { workforceAnomalies } from "../assets/js/modules/workforce-insights-view.js";


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


test("Workforce READY is a calendar-first workspace with compact controls", async () => {
  const [html, page] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
  ]);
  for (const id of [
    "workforceViewState", "workforceReadyView", "workforceImportToggle",
    "workforceSummary", "workforceDateFrom", "workforceDateTo",
    "workforceCalendar", "workforceCoverage", "workforceAnomalies",
    "workforceImportForm", "workforceExportBtn", "workforceTodayBtn",
    "workforcePreviousBtn", "workforceNextBtn", "workforceDatePicker",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(page, /Importa il planning esistente oppure crea il primo planning/);
  assert.doesNotMatch(html, /Apri calendario/);
  assert.match(html, /Aggiorna da Excel/);
  assert.match(page, /await loadCalendar\(\)/);
});


test("Workforce summary is deterministic and uses backend availability", () => {
  const summary = workforceSummary(
    [{}, {}],
    [
      { availability: true, status_code: "scheduled" },
      { availability: false, status_code: "sickness" },
    ],
    [{ margin: -1 }, { margin: 2 }],
  );
  assert.deepEqual(summary, {
    members: 2,
    nextDay: 0,
    sameDay: 0,
    cycleNotSet: 2,
    available: 1,
    scheduled: 1,
    rest: 0,
    absent: 1,
    deficit: 1,
    margin: -1,
    coverageConfigured: true,
  });
  assert.equal(workforceStatusLabel("holiday"), "Ferie");
});


test("Workforce calendar supports day week person and side-panel edits", async () => {
  const [html, page, detail] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/workforce-detail-panel.js"),
  ]);
  for (const mode of ["day", "week", "person"]) {
    assert.match(html, new RegExp(`data-workforce-view-mode="${mode}"`));
  }
  assert.match(page, /saveWorkforceDayStatus/);
  assert.match(page, /updateWorkforceMember/);
  assert.match(page, /source_reference: "manual"/);
  assert.match(page, /workforceDetailPanel\.openStatus/);
  assert.match(detail, /surface\.show/);
  assert.match(detail, /surface\.requestClose/);
  assert.match(html, /id="workforceDetailPanel"[\s\S]*?id="workforceStatusEditor"/);
  assert.match(html, /id="workforceDetailPanel"[\s\S]*?id="workforceMemberEditor"/);
  assert.equal(workforceTimeLabel({ start_time: "08:00", end_time: "17:00" }), "08:00–17:00");
});


test("Workforce shift editing is compact immediate and keyboard accessible", async () => {
  const [html, page, detail, calendar] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/workforce-detail-panel.js"),
    frontendFile("assets/js/modules/workforce-calendar-view.js"),
  ]);
  const editor = html.slice(
    html.indexOf('id="workforceStatusEditor"'),
    html.indexOf('id="workforceMemberDetail"'),
  );
  for (const id of [
    "workforceStatusPerson", "workforceStatusDateLabel", "workforceShiftCode",
    "workforceStatusNotes", "workforceStatusSave", "workforceStatusCancel",
  ]) {
    assert.match(editor, new RegExp(`id="${id}"`));
  }
  assert.equal((editor.match(/name="workforceStatusCode"/g) || []).length, 9);
  assert.match(editor, /value="available_limited"/);
  assert.doesNotMatch(editor, /workforceStatus(Time|Source)|<textarea/);
  assert.match(detail, /surface\.show\(selectedChoice\)/);
  assert.match(detail, /event\.key !== "Enter"/);
  assert.match(detail, /requestSubmit\(byId\("workforceStatusSave"\)\)/);
  assert.match(page, /updateCurrentStatus\(savedStatus\)/);
  assert.match(page, /window\.requestAnimationFrame\(focusSelectedCell\)/);
  assert.match(page, /refreshCoverageAfterStatusSave\(/);
  assert.match(page, /const coverage = await getWorkforceCoverage\(dateFrom, dateTo\)/);
  const submitStart = page.indexOf("async function submitStatus");
  const submitBody = page.slice(submitStart, page.indexOf("async function submitMember", submitStart));
  assert.doesNotMatch(submitBody, /loadCalendar\(/);
  assert.match(calendar, /aria-pressed="\$\{multiSelected \|\| selected\}"/);
  assert.match(calendar, /event\.key === "Enter"[\s\S]*?button\.click\(\)/);
  assert.match(calendar, /target\.focus\(\{ preventScroll: true \}\)/);
});


test("Workforce cell arrow navigation remains inside calendar bounds", () => {
  assert.deepEqual(
    nextWorkforceCellPosition({ row: 1, column: 2 }, "ArrowRight", 3, 7),
    { row: 1, column: 3 },
  );
  assert.deepEqual(
    nextWorkforceCellPosition({ row: 0, column: 0 }, "ArrowUp", 3, 7),
    { row: 0, column: 0 },
  );
  assert.deepEqual(
    nextWorkforceCellPosition({ row: 2, column: 6 }, "ArrowDown", 3, 7),
    { row: 2, column: 6 },
  );
});


test("Workforce main tabs default to Calendar and hide secondary panels", async () => {
  const [html, page] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(html, /id="workforceCalendarTab"[\s\S]*?aria-selected="true"/);
  assert.match(html, /id="workforceCoveragePanel"[\s\S]*?hidden/);
  assert.match(html, /id="workforceAnomaliesPanel"[\s\S]*?hidden/);
  assert.match(page, /const TAB_ORDER = \["calendar", "coverage", "anomalies"\]/);
  assert.match(page, /panel\.hidden = panel\.dataset\.workforcePanel !== activeTab/);
  assert.match(page, /handleTabKeydown/);
});


test("Workforce calendar uses only the current or first available week", () => {
  const current = workforceCalendarWindow({
    summary: { date_from: "2025-12-28", date_to: "2027-01-03" },
  }, "2026-07-21");
  assert.deepEqual(current, {
    dateFrom: "2026-07-20",
    dateTo: "2026-07-26",
  });

  const first = workforceCalendarWindow({
    summary: { date_from: "2027-02-03", date_to: "2027-03-01" },
  }, "2026-07-21");
  assert.deepEqual(first, {
    dateFrom: "2027-02-03",
    dateTo: "2027-02-09",
  });
});


test("Workforce import shows recognized sheets and a strictly bounded preview", async () => {
  const [view, css] = await Promise.all([
    frontendFile("assets/js/modules/workforce-view.js"),
    frontendFile("assets/css/workforce.css"),
  ]);
  assert.match(view, /Planning turni/);
  assert.match(view, /preview\.sheets\.filter/);
  assert.match(view, /\.slice\(0, 5\)/);
  assert.match(view, /Object\.keys\(rows\[0\]\)\.slice\(0, 8\)/);
  assert.match(view, /massimo 5 risorse e 7 giorni/);
  assert.match(css, /max-height: 280px/);
  assert.match(css, /overflow: auto/);
});


test("Workforce initial READY load is limited to the active calendar period", async () => {
  const source = await frontendFile("assets/js/modules/workforce-page.js");
  const calendarStart = source.indexOf("async function loadCalendar");
  const refreshStart = source.indexOf("async function refresh()", calendarStart);
  const calendarBody = source.slice(calendarStart, refreshStart);
  const refreshBody = source.slice(refreshStart, source.indexOf("async function submitStatus", refreshStart));
  assert.match(calendarBody, /getWorkforceCalendar\(dateFrom, dateTo\)/);
  assert.match(calendarBody, /getWorkforceCoverage\(dateFrom, dateTo\)/);
  assert.match(calendarBody, /listWorkforceMembers\(\)/);
  assert.doesNotMatch(calendarBody, /getWorkforceChanges/);
  assert.match(refreshBody, /getWorkforceStatus\(\)/);
  assert.match(refreshBody, /await loadCalendar\(\)/);
});


test("Workforce import has loading guards and closes after success", async () => {
  const source = await frontendFile("assets/js/modules/workforce-import-flow.js");
  assert.match(source, /if \(analyzing \|\| importing\) return/);
  assert.match(source, /setBusy\("analysis"\)/);
  assert.match(source, /setBusy\("import"\)/);
  assert.match(source, /close\(\{ reset: true \}\)/);
  const page = await frontendFile("assets/js/modules/workforce-page.js");
  assert.match(page, /setPageState\(PAGE_STATES\.READY, status\)/);
  assert.match(page, /setPageState\(PAGE_STATES\.EMPTY, status\)/);
});


test("Workforce visible language translates internal states", async () => {
  const [source, insights] = await Promise.all([
    frontendFile("assets/js/modules/workforce-view.js"),
    frontendFile("assets/js/modules/workforce-insights-view.js"),
  ]);
  assert.match(insights, /requirement_unavailable: "Non configurato"/);
  assert.match(source, /scheduled: "Programmato"/);
  assert.match(source, /rest: "Riposo"/);
  assert.equal(workforceStatusLabel("unavailable"), "Non disponibile");
  assert.equal(workforceStatusLabel("not-an-enum"), "Da verificare");
});


test("Workforce anomalies are categorized and initially bounded to 25", async () => {
  const statuses = Array.from({ length: 30 }, (_, index) => ({
    workforce_member_id: 1,
    date: `2026-07-${String((index % 7) + 20).padStart(2, "0")}`,
    status_code: index % 2 ? "sickness" : "rest",
  }));
  const result = workforceAnomalies(statuses, [{ workforce_member_id: 1, display_name: "Risorsa Test" }]);
  assert.equal(result.total, 30);
  assert.equal(result.counts.absence, 15);
  assert.equal(result.counts.rest, 15);
  const [page, insights] = await Promise.all([
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/workforce-insights-view.js"),
  ]);
  assert.match(page, /const ANOMALY_PAGE_SIZE = 25/);
  assert.match(insights, /result\.items\.slice\(0, limit\)/);
  assert.match(page, /anomalyLimit \+= ANOMALY_PAGE_SIZE/);
});


test("Workforce layout is bounded, wide and responsive", async () => {
  const [layout, calendar, panel, responsive] = await Promise.all([
    frontendFile("assets/css/workforce-layout.css"),
    frontendFile("assets/css/workforce-calendar.css"),
    frontendFile("assets/css/workforce-panel.css"),
    frontendFile("assets/css/workforce-responsive.css"),
  ]);
  assert.match(layout, /width: min\(1500px, calc\(100% - 48px\)\)/);
  assert.match(calendar, /height: clamp\(590px,[\s\S]*?720px\)/);
  assert.match(calendar, /position: sticky/);
  assert.match(calendar, /\.workforce-day-list/);
  assert.match(panel, /\.workforce-detail-panel/);
  assert.match(
    panel,
    /\.workforce-overlay-backdrop:hover:not\(:disabled\)[\s\S]*?background: rgb\(18 29 26 \/ 58%\)/,
  );
  assert.match(responsive, /@media \(max-width: 1180px\)/);
  assert.match(responsive, /@media \(max-width: 720px\)/);
  assert.match(responsive, /@media \(max-width: 620px\)/);
  assert.match(
    responsive,
    /@media \(max-width: 720px\)[\s\S]*?\.workforce-kpis[\s\S]*?grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)[\s\S]*?overflow-x: visible/,
  );
  assert.doesNotMatch(
    responsive,
    /\.workforce-kpis\s*\{[\s\S]{0,180}?overflow-x: auto/,
  );
});


test("Workforce polish keeps operational signals compact and accessible", async () => {
  const [html, page, calendar, insights, layout, calendarCss, panelCss] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/workforce-calendar-view.js"),
    frontendFile("assets/js/modules/workforce-insights-view.js"),
    frontendFile("assets/css/workforce-layout.css"),
    frontendFile("assets/css/workforce-calendar.css"),
    frontendFile("assets/css/workforce-panel.css"),
  ]);
  assert.match(html, /aria-label="Settimana precedente"[\s\S]*?&larr;/);
  assert.match(html, /id="workforceCalendarWindow" class="workforce-period-focus"/);
  const workforce = html.slice(
    html.indexOf('id="workforceSection"'),
    html.indexOf('id="fleetPluginSection"'),
  );
  assert.equal((workforce.match(/data-kpi=/g) || []).length, 10);
  assert.match(calendar, /class="workforce-status-badge"/);
  assert.match(calendarCss, /\.workforce-status-badge::before/);
  assert.match(insights, /covered: "Coperto"/);
  assert.match(insights, /deficit: "Scoperto"/);
  assert.match(insights, /eventi registrati nel periodo selezionato/);
  assert.match(page, /showWorkforceFeedback\("Modifica salvata"\)/);
  assert.match(page, /}, 3200\)/);
  assert.match(layout, /transition:[^;]*160ms/);
  assert.match(panelCss, /180ms ease-out/);
});


test("Workforce dialogs trap focus and expose accessible tabs and tables", async () => {
  const [html, surface, calendar] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workforce-surface.js"),
    frontendFile("assets/js/modules/workforce-calendar-view.js"),
  ]);
  assert.match(html, /id="workforceImportPanel"[\s\S]*?role="dialog"[\s\S]*?aria-modal="true"/);
  assert.match(html, /role="tablist" aria-label="Aree Planning turni"/);
  assert.match(html, /role="tabpanel"/);
  assert.match(surface, /event\.key !== "Tab"/);
  assert.match(surface, /event\.key === "Escape"/);
  assert.match(calendar, /<caption class="visually-hidden">/);
  assert.match(calendar, /scope="row"/);
});


test("Workforce expected disabled state is handled without console noise", async () => {
  const source = await frontendFile("assets/js/modules/workforce-page.js");
  assert.match(source, /isExpectedApiError\(error, \{ statuses: \[404\] \}\)/);
  assert.match(source, /dataset\.pageState = PAGE_STATES\.EMPTY/);
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
    frontendFile("assets/js/modules/workforce-import-flow.js"),
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


test("Workforce P1 prioritizes critical and attention KPIs without changing metrics", async () => {
  const [view, css] = await Promise.all([
    frontendFile("assets/js/modules/workforce-view.js"),
    frontendFile("assets/css/workforce-layout.css"),
  ]);

  assert.match(view, /resources: "normal"/);
  assert.match(view, /summary\.absent > 0 \? "attention" : "normal"/);
  assert.match(view, /summary\.deficit > 0 \? "critical" : "normal"/);
  assert.match(view, /dataset\.priority = priority/);
  assert.match(css, /\.workforce-kpis > div\[data-priority="attention"\]/);
  assert.match(css, /\.workforce-kpis > div\[data-priority="critical"\]/);
  assert.match(
    css,
    /\.workforce-kpis > div\[data-priority="critical"\] dd[\s\S]*?color: var\(--critical-text\)/,
  );
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


test("Workforce import exposes deterministic stages without fake percentages", async () => {
  const [flow, page, lifecycle, css, responsive] = await Promise.all([
    frontendFile("assets/js/modules/workforce-import-flow.js"),
    frontendFile("assets/js/modules/workforce-page.js"),
    frontendFile("assets/js/modules/workspace-lifecycle.js"),
    frontendFile("assets/css/workforce.css"),
    frontendFile("assets/css/responsive.css"),
  ]);
  for (const label of [
    "Lettura file",
    "Analisi fogli",
    "Preparazione risorse",
    "Preparazione calendario",
    "Salvataggio",
    "Verifica finale",
  ]) {
    assert.match(flow, new RegExp(label));
  }
  assert.match(flow, /Fasi di elaborazione del file/);
  assert.match(flow, /window\.setInterval/);
  assert.doesNotMatch(flow, /role="progressbar"|aria-valuenow|\d+%/);
  assert.match(page, /workforce:data-imported/);
  assert.doesNotMatch(page, /operations:data-imported/);
  assert.match(lifecycle, /workforce:data-imported/);
  assert.match(css, /\.workforce-import-progress/);
  assert.match(responsive, /\.workforce-import-progress ol[\s\S]*?grid-template-columns: 1fr/);
});

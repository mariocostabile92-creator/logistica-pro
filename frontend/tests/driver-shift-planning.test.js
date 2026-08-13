import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  renderMergeRows,
  renderMergeSummary,
  renderPagination,
  renderPlanningHeader,
  renderSources,
} from "../assets/js/modules/driver-shift-planning-presenter.js";
import {
  createDriverShiftPlanningState,
  DRIVER_SHIFT_PAGE_SIZE,
} from "../assets/js/modules/driver-shift-planning-state.js";


const source = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "", textContent: "", hidden: false, disabled: false });

const referenceA = {
  source_row_id: 101,
  workforce_import_id: 1, filename: "Planning_A.xlsx", sheet: "Planning",
  row_number: 27, source_record_key: "a", source_order: 0,
};
const referenceB = {
  source_row_id: 202,
  workforce_import_id: 2, filename: "Planning_B.xlsx", sheet: "Driver",
  row_number: 84, source_record_key: "b", source_order: 1,
};

function row(classification, overrides = {}) {
  return {
    identity_key: "member:1",
    workforce_member_id: 1,
    source_external_identifier: "WF-1",
    display_name: "Mario Rossi",
    operational_date: "2026-01-03",
    status_code: "scheduled",
    availability: true,
    shift_code: "A",
    station: "DLO2",
    transporter_id: "T-100",
    classification,
    conflict_key: `conflict-${classification}`,
    resolved: !["POTENTIAL_CONFLICT", "IDENTITY_CONFLICT", "UNRESOLVED_IDENTITY"].includes(classification),
    resolution: null,
    source_references: [referenceA],
    conflicting_alternatives: [],
    ...overrides,
  };
}


test("Fonti turni is a Workforce entry point, not a primary navbar item", async () => {
  const html = await source("index.html");
  const workforce = html.slice(html.indexOf('id="workforceSection"'), html.indexOf('id="fleetPluginSection"'));
  assert.match(workforce, /id="driverShiftPlanningSection"/);
  assert.match(workforce, />Fonti turni</);
  assert.doesNotMatch(html.slice(0, html.indexOf('id="workforceSection"')), />Fonti turni</);
});


test("logical planning header shows label period DRAFT source count version and update", () => {
  const target = element();
  renderPlanningHeader(target, {
    label: "Planning annuale", period_start: "2025-12-28",
    period_end: "2027-01-03", version: 3,
    updated_at: "2026-08-11T10:30:00Z",
  }, 2);
  assert.match(target.innerHTML, /Planning annuale/);
  assert.match(target.innerHTML, /BOZZA/);
  assert.match(target.innerHTML, /2 fonti/);
  assert.match(target.innerHTML, /v3/);
});


test("source cards expose filename import date range rows compatibility and merge availability", () => {
  const target = element();
  renderSources(target, [{
    id: 1, source_filename: "Planning_A.xlsx", imported_at: "2026-08-11T10:00:00Z",
    row_count: 82, date_from: "2025-12-28", date_to: "2026-12-31",
    period_compatibility: "COMPATIBLE", status: "AVAILABLE", warnings: [],
  }]);
  for (const expected of ["Planning_A.xlsx", "82", "COMPATIBLE", "Disponibile"])
    assert.match(target.innerHTML, new RegExp(expected));
});


test("remove copy removes only the relation and never says delete file", () => {
  const target = element();
  renderSources(target, [{
    id: 7, source_filename: "A.xlsx", imported_at: "2026-08-11T10:00:00Z",
    row_count: 1, date_from: "2026-01-01", date_to: "2026-01-01",
    period_compatibility: "COMPATIBLE", status: "AVAILABLE", warnings: [],
  }]);
  assert.match(target.innerHTML, /Rimuovi dalla combinazione/);
  assert.doesNotMatch(target.innerHTML, /Elimina file/);
});


test("merge summary renders publish readiness and real unified counters", () => {
  const target = element();
  renderMergeSummary(target, {
    total_source_rows: 143, unified_rows: 139, exact_duplicates: 2,
    potential_conflicts: 1, identity_conflicts: 0, unresolved_rows: 1,
    conflicts_to_resolve: 2, conflicts_resolved: 3,
    unresolved_identities: 1, ready_to_publish: false,
  });
  for (const label of ["Da risolvere", "Risolti", "Identità non risolte", "Pronto per pubblicare", "Righe sorgente", "Righe unificate"])
    assert.match(target.innerHTML, new RegExp(label));
  assert.match(target.innerHTML, /143/);
  assert.match(target.innerHTML, /139/);
});


test("exact duplicate is one card with multi-source provenance", () => {
  const target = element();
  renderMergeRows(target, {
    rows: [row("EXACT_DUPLICATE", { source_references: [referenceA, referenceB] })],
  });
  assert.equal((target.innerHTML.match(/class="driver-shift-row /g) || []).length, 1);
  assert.match(target.innerHTML, /Duplicato esatto/);
  assert.match(target.innerHTML, /Planning_A.xlsx/);
  assert.match(target.innerHTML, /Planning_B.xlsx/);
});


test("potential conflict compares alternatives and offers explicit source choices", () => {
  const target = element();
  renderMergeRows(target, { rows: [row("POTENTIAL_CONFLICT", {
    conflicting_alternatives: [
      { driver_display_name: "Mario Rossi", shift_code: "A", status_code: "scheduled", source_references: [referenceA] },
      { driver_display_name: "Mario Rossi", shift_code: "B", status_code: "scheduled", source_references: [referenceB] },
    ],
  })] });
  assert.match(target.innerHTML, /Valori dalle fonti/);
  assert.match(target.innerHTML, /seleziona esplicitamente la fonte autorevole/);
  assert.match(target.innerHTML, />A · scheduled</);
  assert.match(target.innerHTML, />B · scheduled</);
  assert.equal((target.innerHTML.match(/Usa questa fonte/g) || []).length, 2);
  assert.match(target.innerHTML, /Escludi questa giornata/);
});


test("identity conflict explains the same T-ID across different drivers", () => {
  const target = element();
  renderMergeRows(target, { rows: [row("IDENTITY_CONFLICT", {
    conflicting_alternatives: [
      { driver_display_name: "Mario Rossi", transporter_id: "T-100", source_references: [referenceA] },
      { driver_display_name: "Luigi Bianchi", transporter_id: "T-100", source_references: [referenceB] },
    ],
  })] });
  assert.match(target.innerHTML, /Lo stesso T-ID è associato a driver differenti/);
  assert.match(target.innerHTML, /Mario Rossi/);
  assert.match(target.innerHTML, /Luigi Bianchi/);
});


test("unresolved identity remains visible and does not create a member", () => {
  const target = element();
  renderMergeRows(target, { rows: [row("UNRESOLVED_IDENTITY", {
    identity_key: null, display_name: null, source_external_identifier: null,
  })] });
  assert.match(target.innerHTML, /Driver non risolto/);
  assert.match(target.innerHTML, /Associa un membro Workforce/);
  assert.match(target.innerHTML, /Associa e usa/);
});


test("preview filters cover all five classifications plus all", async () => {
  const html = await source("index.html");
  for (const value of ["", "DISTINCT_ASSIGNMENT", "EXACT_DUPLICATE", "POTENTIAL_CONFLICT", "IDENTITY_CONFLICT", "UNRESOLVED_IDENTITY"])
    assert.match(html, new RegExp(`data-driver-shift-filter="${value}"`));
});


test("driver and T-ID search is debounced and sent to the API", async () => {
  const [controller, api] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"),
    source("assets/js/api.js"),
  ]);
  assert.match(controller, /setTimeout[\s\S]*250/);
  assert.match(api, /params\.set\("search", search\)/);
  assert.match(api, /classification/);
});


test("pagination is server-side and presenter exposes page boundaries", async () => {
  const api = await source("assets/js/api.js");
  assert.match(api, /limit = 25/);
  assert.match(api, /offset = 0/);
  assert.equal(DRIVER_SHIFT_PAGE_SIZE, 25);
  const previous = element();
  const next = element();
  const status = element();
  renderPagination({ previous, next, status }, {
    filtered_rows: 80, offset: 25, rows: Array(25), has_more: true,
  });
  assert.equal(status.textContent, "26–50 di 80");
  assert.equal(previous.disabled, false);
  assert.equal(next.disabled, false);
});


test("state request versions reject stale preview races", () => {
  const store = createDriverShiftPlanningState();
  const first = store.beginRequest();
  const second = store.beginRequest();
  assert.equal(store.isCurrent(first), false);
  assert.equal(store.isCurrent(second), true);
  assert.equal(store.completeRequest(first), false);
});


test("add source reuses the existing Workforce import parser and refreshes", async () => {
  const [controller, importFlow] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"),
    source("assets/js/modules/workforce-import-flow.js"),
  ]);
  assert.match(controller, /startImport\("add"\)/);
  assert.match(controller, /await resolveImport\(result\.fingerprint/);
  assert.match(controller, /await addSource/);
  assert.match(controller, /await refresh\(state\.planning\.id\)/);
  assert.match(importFlow, /previewWorkforceImport/);
  assert.match(importFlow, /confirmWorkforceImport/);
});


test("first imported source suggests its detected period before explicit planning creation", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /openCreateDialog\(preview\)/);
  assert.match(controller, /suggestion\?\.date_from/);
  assert.match(controller, /suggestion\?\.date_to/);
  assert.match(controller, /Il periodo del file non coincide/);
});


test("replace is explicit, preserves history copy, and updates only the DRAFT set", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-planning.js"),
  ]);
  assert.match(html, /Le fonti precedenti resteranno nello storico import/);
  assert.match(controller, /startImport\("replace"\)/);
  assert.match(controller, /await replaceSources\(state\.planning\.id, \[importId\]\)/);
});


test("remove requires an accessible confirmation and refreshes the preview", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-planning.js"),
  ]);
  assert.match(html, /id="driverShiftRemoveDialog"[\s\S]*aria-labelledby="driverShiftRemoveTitle"/);
  assert.match(controller, /await removeSource/);
  assert.match(controller, /await refresh\(state\.planning\.id\)/);
});


test("Q5 UI exposes explicit resolve and publish actions without silent publish", async () => {
  const html = await source("index.html");
  const section = html.slice(
    html.indexOf('id="driverShiftPlanningSection"'),
    html.indexOf('id="workforceReadyView"'),
  );
  assert.match(section, /id="driverShiftResolveBtn"[^>]*>Risolvi conflitti/);
  assert.match(section, /id="driverShiftPublishBtn"[^>]*>Pubblica turni unificati/);
  assert.match(section, /id="driverShiftPublishDialog"/);
  assert.match(section, /non modifica ancora i turni operativi/);
});


test("one-source UX remains a normal source card without multi-source assumptions", () => {
  const target = element();
  renderSources(target, [{
    id: 1, source_filename: "Solo.xlsx", imported_at: "2026-08-11T10:00:00Z",
    row_count: 10, date_from: "2026-01-01", date_to: "2026-01-31",
    period_compatibility: "COMPATIBLE", status: "AVAILABLE", warnings: [],
  }]);
  assert.equal((target.innerHTML.match(/driver-shift-source-card/g) || []).length, 1);
  assert.match(target.innerHTML, /Solo.xlsx/);
});


test("controller uses a dedicated API client and contains no direct fetch", async () => {
  const [controller, client] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"),
    source("assets/js/modules/driver-shift-planning-api.js"),
  ]);
  assert.doesNotMatch(controller, /fetch\s*\(/);
  assert.match(client, /createDriverShiftPlanning as createPlanning/);
  assert.match(client, /getCurrentDriverShiftPlanning as getCurrentPlanning/);
  assert.match(client, /getDriverShiftPlanningMergePreview as getMergePreview/);
});


test("multiple plannings can be selected and current is not inferred from the last numeric ID", async () => {
  const [controller, html] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"), source("index.html"),
  ]);
  assert.match(html, /id="driverShiftPlanningSelector"/);
  assert.match(controller, /collection\.current/);
  assert.match(controller, /state\.plannings\.find/);
  assert.doesNotMatch(controller, /Math\.max[\s\S]*planning/);
});


test("responsive CSS covers desktop tablet and 390 px without a fixed canvas", async () => {
  const css = await source("assets/css/driver-shift-planning.css");
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.match(css, /min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});


test("mobile cards, provenance and controls wrap without horizontal overflow", async () => {
  const css = await source("assets/css/driver-shift-planning.css");
  assert.match(css, /overflow-wrap: anywhere/);
  assert.match(css, /\.driver-shift-source-list,[\s\S]*\.driver-shift-rows[\s\S]*grid-template-columns: 1fr/);
  assert.match(css, /\.driver-shift-actions label,[\s\S]*width: 100%/);
});


test("accessibility uses text statuses keyboard-native controls live regions and labelled dialogs", async () => {
  const html = await source("index.html");
  assert.match(html, /aria-label="Filtra righe preview"/);
  assert.match(html, /id="driverShiftMergeRows"[^>]*aria-live="polite"/);
  assert.match(html, /id="driverShiftPlanningDialog"[^>]*aria-labelledby/);
  assert.match(html, /id="driverShiftReplaceDialog"[^>]*aria-labelledby/);
  assert.doesNotMatch(html, /onclick=/);
});


test("import flow forwards persisted fingerprint result and detected preview", async () => {
  const flow = await source("assets/js/modules/workforce-import-flow.js");
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(flow, /const confirmedPreview = importPreview/);
  assert.match(flow, /afterImport\(result, confirmedPreview\)/);
  assert.match(page, /handleImported\(result, preview\)/);
});


test("workspace loader loads Q5 styles only with Workforce", async () => {
  const loader = await source("assets/js/modules/workspace-loader.js");
  assert.match(loader, /driver-shift-planning\.css\?v=4/);
  assert.match(loader, /import\("\.\/workforce-page\.js\?v=33"\)/);
});


test("resolved conflict state is visible and keeps source provenance", () => {
  const target = element();
  renderMergeRows(target, { rows: [row("POTENTIAL_CONFLICT", {
    resolved: true,
    resolution: { resolution_type: "USE_SOURCE_ROW", selected_source_row_id: 101 },
    conflicting_alternatives: [
      { driver_display_name: "Mario Rossi", shift_code: "A", source_references: [referenceA] },
    ],
  })] });
  assert.match(target.innerHTML, /Risolto: fonte selezionata/);
  assert.match(target.innerHTML, /Planning_A.xlsx/);
  assert.doesNotMatch(target.innerHTML, /Escludi questa giornata/);
});


test("publish CTA is controlled by backend readiness and always uses confirmation", async () => {
  const [controller, html] = await Promise.all([
    source("assets/js/modules/driver-shift-planning.js"), source("index.html"),
  ]);
  assert.match(controller, /publishButton\.disabled = !state\.preview\?\.summary\?\.ready_to_publish/);
  assert.match(controller, /openPublishDialog/);
  assert.match(controller, /expected_preview_fingerprint: state\.preview\.preview_fingerprint/);
  assert.match(html, /Questi turni diventeranno la vista operativa Workforce/);
  assert.doesNotMatch(controller, /addSource[\s\S]{0,100}publishPlanning/);
});


test("stale publish response reloads preview instead of overwriting state", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /error\?\.status === 409/);
  assert.match(controller, /La preview è cambiata/);
  assert.match(controller, /await refreshPreview\(\)/);
});


test("ACTIVE planning disables source mutations and offers a new revision", async () => {
  const controller = await source("assets/js/modules/driver-shift-planning.js");
  assert.match(controller, /state\.planning\.status !== "DRAFT"/);
  assert.match(controller, /elements\.draftNotice\.hidden = !isDraft/);
  assert.match(controller, /revisionButton\.hidden = state\.planning\.status !== "ACTIVE"/);
  assert.match(controller, /await createRevision\(state\.planning\.id\)/);
});


test("single-source ready preview can publish directly", () => {
  const target = element();
  renderMergeSummary(target, {
    conflicts_to_resolve: 0, conflicts_resolved: 0,
    unresolved_identities: 0, ready_to_publish: true,
    total_source_rows: 10, unified_rows: 10,
  });
  assert.match(target.innerHTML, /Pronto per pubblicare/);
  assert.match(target.innerHTML, /SÌ/);
});


test("Workforce refreshes only after successful publication", async () => {
  const page = await source("assets/js/modules/workforce-page.js");
  assert.match(page, /type !== "published"/);
  assert.match(page, /calendarLoaded = false/);
  assert.match(page, /await loadFromAnchor\(periodStart/);
});


test("mobile conflict resolution and publish dialog remain one column", async () => {
  const css = await source("assets/css/driver-shift-planning.css");
  assert.match(css, /\.driver-shift-resolution,[\s\S]*width: 100%/);
  assert.match(css, /\.driver-shift-publish-summary,[\s\S]*grid-template-columns: 1fr/);
});

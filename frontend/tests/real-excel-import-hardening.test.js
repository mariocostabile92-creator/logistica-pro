import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  collectMapping,
  workbookTypeLabel,
} from "../assets/js/modules/import-preview.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


test("workbook summary exposes type sheet header rows and confidence", async () => {
  const source = await frontendFile(
    "assets/js/modules/import-preview.js",
  );

  for (const field of [
    "workbook_type",
    "workbook_type_confidence",
    "original_filename",
    "selected_sheet",
    "selected_header_row",
    "total_rows",
  ]) {
    assert.match(source, new RegExp(field));
  }
  assert.match(source, /Struttura rilevata/);
});


test("all explicit workbook types have readable labels", () => {
  assert.equal(
    workbookTypeLabel("DAILY_OPERATIONAL_PLANNING"),
    "Planning operativo giornaliero",
  );
  assert.equal(
    workbookTypeLabel("WORKFORCE_SCHEDULE"),
    "Programmazione turni driver",
  );
  assert.equal(workbookTypeLabel("FLEET_REGISTRY"), "Registro Fleet");
  assert.equal(
    workbookTypeLabel("UNKNOWN_WORKBOOK"),
    "Workbook non riconosciuto",
  );
});


test("compatibility warnings come from typed backend issues", async () => {
  const [preview, importer] = await Promise.all([
    frontendFile("assets/js/modules/import-preview.js"),
    frontendFile("assets/js/modules/import-workbook.js"),
  ]);

  assert.match(preview, /blockingReasons/);
  assert.match(preview, /Da risolvere/);
  assert.match(importer, /item\.code === "WORKBOOK_TYPE_MISMATCH"/);
  assert.doesNotMatch(importer, /WORKFORCE_SCHEDULE/);
});


test("sheet and header changes require a fresh backend analysis", async () => {
  const source = await frontendFile(
    "assets/js/modules/import-workbook.js",
  );

  assert.match(source, /elements\.sheet\.addEventListener\("change", markStructureStale\)/);
  assert.match(source, /elements\.header\.addEventListener\("input", markStructureStale\)/);
  assert.match(source, /Da rianalizzare/);
  assert.match(source, /previewImport/);
});


test("mapping is compact selectable and restricted to backend options", async () => {
  const source = await frontendFile(
    "assets/js/modules/import-preview.js",
  );

  assert.match(source, /<details class="mapping-details" open>/);
  assert.match(source, /data-mapping-source/);
  assert.match(source, /options\.map/);
  assert.match(source, /Campo riconosciuto|Mapping colonne/);
});


test("ignore column is an explicit mapping action", () => {
  const container = {
    querySelectorAll() {
      return [
        {
          value: "__ignore__",
          dataset: { mappingSource: "Decorative" },
        },
        {
          value: "vehicle_plate",
          dataset: { mappingSource: "Plate" },
        },
        {
          value: "__unassigned__",
          dataset: { mappingSource: "Unknown" },
        },
      ];
    },
  };

  assert.deepEqual(collectMapping(container), [
    { source_column: "Decorative", target_field: null },
    { source_column: "Plate", target_field: "vehicle_plate" },
  ]);
});


test("sample table is bounded by backend and horizontally scrollable", async () => {
  const [source, css] = await Promise.all([
    frontendFile("assets/js/modules/import-preview.js"),
    frontendFile("assets/css/excel-import.css"),
  ]);

  assert.match(source, /Prime \$\{rows\.length\} righe utili/);
  assert.match(source, /<table>/);
  assert.match(css, /max-height: 480px/);
  const components = await frontendFile("assets/css/components.css");
  assert.match(components, /\.table-wrap[\s\S]*overflow-x: auto/);
});


test("import starts disabled and is enabled only by compatible analysis", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/import-workbook.js"),
  ]);

  assert.match(
    html,
    /id="planningPreviewBtn"[\s\S]*?<button type="submit" class="secondary" disabled>/,
  );
  assert.match(
    html,
    /id="fleetPreviewBtn"[\s\S]*?<button type="submit" class="secondary" disabled>/,
  );
  assert.match(source, /elements\.submit\.disabled = !importAllowed/);
  assert.match(source, /allowed: data\.import_allowed/);
});


test("typed import errors are presented without frontend classification", async () => {
  const source = await frontendFile(
    "assets/js/modules/import-workbook.js",
  );

  assert.match(source, /userErrorPresentation/);
  assert.match(source, /showImportError\(`imports\.\$\{datasetType\}`/);
  assert.doesNotMatch(source, /calculate|classifyWorkbook|daily_required/);
});


test("expected empty API states do not use red console logging", async () => {
  const paths = [
    "assets/js/modules/demo-workspace.js",
    "assets/js/modules/planning-page.js",
    "assets/js/modules/operations-dashboard.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));

  assert.match(sources[0], /isExpectedApiError\(error, \{ statuses: \[404\] \}\)/);
  assert.match(sources[1], /isExpectedApiError\(error, \{ statuses: \[404\] \}\)/);
  assert.match(sources[2], /statuses: \[400\]/);
  assert.doesNotMatch(sources.join("\n"), /console\.(error|warn|log)/);
});


test("Planning generation is blocked before a valid import", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/planning-page.js"),
  ]);

  assert.match(html, /id="generatePlanningBtn"[\s\S]*disabled/);
  assert.match(html, /Importa prima un Planning operativo giornaliero valido\./);
  assert.match(source, /if \(!hasValidPlanningImport\)/);
  assert.match(source, /latest_planning_import/);
});


test("import controls are accessible and have live result regions", async () => {
  const html = await frontendFile("index.html");

  for (const id of [
    "planningProfile",
    "planningIssues",
    "fleetProfile",
    "fleetIssues",
  ]) {
    assert.match(
      html,
      new RegExp(`id="${id}"[^>]*aria-live="polite"`),
    );
  }
  assert.match(html, /aria-describedby="planningGenerateHint"/);
  assert.match(html, /inputmode="numeric"/);
});


test("import layout covers desktop tablet and mobile without fixed width", async () => {
  const css = await frontendFile("assets/css/excel-import.css");

  assert.match(css, /grid-template-columns: repeat\(5, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /\.mapping-row[\s\S]*grid-template-columns: 1fr/);
  assert.doesNotMatch(css, /width:\s*[1-9]\d{3,}px/);
});


test("wide workbooks and many sheets remain bounded", async () => {
  const [preview, css] = await Promise.all([
    frontendFile("assets/js/modules/import-preview.js"),
    frontendFile("assets/css/excel-import.css"),
  ]);

  assert.match(preview, /profiles\.forEach/);
  assert.match(preview, /mappings\.length/);
  assert.match(css, /overflow-y: auto/);
  assert.match(css, /overflow-wrap: anywhere/);
});


test("import modules contain no console noise or direct fetch calls", async () => {
  const paths = [
    "assets/js/modules/import-workbook.js",
    "assets/js/modules/import-preview.js",
    "assets/js/modules/import-planning.js",
    "assets/js/modules/import-fleet.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));
  const combined = sources.join("\n");

  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
  assert.doesNotMatch(combined, /fetch\(/);
});

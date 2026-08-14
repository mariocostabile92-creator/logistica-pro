import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  orderedSignals,
  partialSourceItems,
  rowTone,
} from "../assets/js/modules/dsp-workspace/presentation.js";
import {
  applyDspWorkspaceEvent,
  createDspWorkspaceState,
  deriveDspWorkspaceView,
} from "../assets/js/modules/dsp-workspace/state.js";
import { rowMarkup } from "../assets/js/modules/dsp-workspace/presenter.js";


const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const DAY = "2026-08-09";

function row(id = 1, overrides = {}) {
  return {
    assignment_id: id,
    route: `R-${id}`,
    wave: "W-1",
    driver: { planning_identifier: `DRV-${id}`, workforce_member_id: id, name: `Driver ${id}` },
    vehicle: { planning_identifier: `V-${id}`, fleet_asset_id: id, plate: `AA${id}`, model: "Van" },
    workforce: { availability_status: "available", convocable: true, reason: "Nessuna limitazione." },
    fleet: { availability: "available", operational_status: "available" },
    journal: { available: true, check_out_status: "completed", check_in_status: "pending", partial: false },
    damage: { available: true, open_cases_count: 0, relevant_case_ids: [], partial: false },
    attention_codes: [],
    ...overrides,
  };
}

function viewFor(rows, signals = [], overrides = {}) {
  const state = applyDspWorkspaceEvent(
    createDspWorkspaceState({ operationDate: DAY }),
    {
      type: "load-completed",
      snapshot: {
        operation_date: DAY,
        planning: { available: true, status: "published" },
        sources: {},
        rows,
        signals,
        ...overrides,
      },
    },
  );
  return deriveDspWorkspaceView(state);
}


test("critical is presented before warning and info without changing backend data", () => {
  const source = [
    { code: "JOURNAL_IN_PROGRESS", severity: "info" },
    { code: "JOURNAL_ANOMALY", severity: "warning" },
    { code: "VEHICLE_NOT_AVAILABLE", severity: "critical" },
  ];
  assert.deepEqual(orderedSignals(source).map((item) => item.severity), [
    "critical", "warning", "info",
  ]);
  assert.equal(source[0].severity, "info");
});

test("primary action follows the most severe signal after view derivation", () => {
  const view = viewFor([row(1)], [
    { code: "JOURNAL_ANOMALY", severity: "warning", assignment_id: 1 },
    { code: "VEHICLE_NOT_AVAILABLE", severity: "critical", assignment_id: 1 },
  ]);
  const markup = rowMarkup(view.rows[0], { canPermission: () => true });
  assert.match(markup, /class="primary"[\s\S]*Apri mezzo/);
});

test("normal and attention rows have distinct, semantic presentation", () => {
  const clear = viewFor([row(1)]).rows[0];
  const critical = viewFor([row(2)], [{
    code: "DRIVER_NOT_AVAILABLE", severity: "critical", assignment_id: 2,
  }]).rows[0];
  assert.match(rowMarkup(clear), /dsp-board-row is-clear/);
  assert.equal(rowTone(critical), "critical");
  assert.match(rowMarkup(critical), /has-attention tone-critical/);
});

test("multiple signals are grouped behind a compact disclosure", () => {
  const critical = viewFor([row(2)], [
    { code: "DRIVER_NOT_AVAILABLE", severity: "critical", assignment_id: 2 },
    { code: "JOURNAL_ANOMALY", severity: "warning", assignment_id: 2 },
    { code: "JOURNAL_IN_PROGRESS", severity: "info", assignment_id: 2 },
  ]).rows[0];
  const markup = rowMarkup(critical);
  assert.match(markup, /Driver non disponibile[\s\S]*\+2 altre/);
  assert.match(markup, /Mostra altre 2 criticità/);
});

test("summary exposes planned drivers, availability, absences and attention", async () => {
  const html = await file("index.html");
  const summary = html.match(/<dl class="dsp-summary"[\s\S]*?<\/dl>/)?.[0] || "";
  assert.equal((summary.match(/<dt>/g) || []).length, 4);
  assert.match(summary, /Driver pianificati[\s\S]*Disponibili[\s\S]*Assenze[\s\S]*Criticità/);
});

test("partial sources expose one grouped disclosure with source details", async () => {
  const items = partialSourceItems({
    workforce: { available: true, partial: true },
    journal: { available: false, partial: true },
  });
  assert.deepEqual(items.map((item) => item.label), ["Workforce", "Journal"]);
  const presenter = await file("assets/js/modules/dsp-workspace/presenter.js");
  assert.match(presenter, /Alcune fonti dati sono parzialmente disponibili/);
  assert.match(presenter, /dsp-source-count/);
});

test("responsive rules preserve zero overflow and 44px mobile targets", async () => {
  const css = await file("assets/css/dsp-workspace.css");
  for (const breakpoint of ["1180", "820", "620"]) {
    assert.match(css, new RegExp(`@media \\(max-width: ${breakpoint}px\\)`));
  }
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.dsp-row-actions[\s\S]*min-height: 44px/);
  assert.match(css, /min-width: 0/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1024|1440)px/);
});

test("DSP controls expose visible keyboard focus", async () => {
  const css = await file("assets/css/dsp-workspace.css");
  assert.match(css, /:focus-visible[\s\S]*outline:/);
});

test("100 rows derive and render without functional regression", () => {
  const rows = Array.from({ length: 100 }, (_, index) => row(index + 1));
  const signals = rows.flatMap((item, index) => (
    index % 5 === 0
      ? [{ code: "JOURNAL_ANOMALY", severity: "warning", assignment_id: item.assignment_id }]
      : []
  ));
  const started = performance.now();
  const view = viewFor(rows, signals);
  const markup = view.rows.map((item) => rowMarkup(item)).join("");
  const elapsed = performance.now() - started;
  assert.equal(view.rows.length, 100);
  assert.equal((markup.match(/<article/g) || []).length, 100);
  assert.ok(elapsed < 250, `Rendering presenter troppo lento: ${elapsed.toFixed(1)}ms`);
});

test("technical signal codes never become visible labels", () => {
  const critical = viewFor([row(2)], [{
    code: "HIGH_SEVERITY_DAMAGE", severity: "critical", assignment_id: 2,
  }]).rows[0];
  const markup = rowMarkup(critical);
  assert.doesNotMatch(markup, /HIGH_SEVERITY_DAMAGE/);
  assert.match(markup, /Danno ad alta gravità/);
});

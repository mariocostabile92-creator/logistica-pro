import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  canConfirmWorkspaceReset,
  createWorkspaceState,
  deriveWorkspaceView,
  importFlowForState,
  WORKSPACE_STATES,
} from "../assets/js/modules/workspace-state.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


function status(workspaceState, overrides = {}) {
  return {
    workspace_state: workspaceState,
    is_demo: workspaceState === WORKSPACE_STATES.DEMO,
    demo_enabled: true,
    latest_planning_import: null,
    latest_fleet_import: null,
    task_count: 0,
    asset_count: 0,
    planning_count: 0,
    briefing_count: 0,
    last_operational_update: null,
    can_reset: workspaceState !== WORKSPACE_STATES.EMPTY,
    available_actions: [],
    ...overrides,
  };
}


function view(workspaceState, overrides = {}) {
  return deriveWorkspaceView(createWorkspaceState({
    loading: false,
    status: status(workspaceState, overrides),
  }));
}


test("badge EMPTY uses explicit text and neutral tone", () => {
  const current = view(WORKSPACE_STATES.EMPTY);
  assert.equal(current.label, "Workspace vuoto");
  assert.equal(current.tone, "empty");
});


test("badge DEMO uses explicit text and demo tone", () => {
  const current = view(WORKSPACE_STATES.DEMO);
  assert.equal(current.label, "Workspace demo");
  assert.equal(current.tone, "demo");
});


test("badge PRODUCTION uses explicit text and production tone", () => {
  const current = view(WORKSPACE_STATES.PRODUCTION);
  assert.equal(current.label, "Workspace produzione");
  assert.equal(current.tone, "production");
});


test("workspace card contains source files counts and update fields", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workspace-card.js"),
  ]);
  assert.match(html, /id="workspaceCurrentCard"/);
  for (const label of [
    "File Planning",
    "Import Planning",
    "File Fleet",
    "Import Fleet",
    "Task",
    "Asset",
    "Briefing",
    "Ultimo aggiornamento",
  ]) {
    assert.match(source, new RegExp(label));
  }
});


test("EMPTY exposes Importa dati as primary action", () => {
  const current = view(WORKSPACE_STATES.EMPTY);
  assert.equal(current.importLabel, "Importa dati");
  assert.equal(current.actions.import, true);
});


test("Carica demo appears only when backend enables it", () => {
  assert.equal(
    view(WORKSPACE_STATES.EMPTY, { demo_enabled: true }).actions.loadDemo,
    true,
  );
  assert.equal(
    view(WORKSPACE_STATES.EMPTY, { demo_enabled: false }).actions.loadDemo,
    false,
  );
  assert.equal(view(WORKSPACE_STATES.PRODUCTION).actions.loadDemo, false);
});


test("reset action is available only for non-empty workspaces", () => {
  assert.equal(view(WORKSPACE_STATES.EMPTY).actions.reset, false);
  assert.equal(view(WORKSPACE_STATES.DEMO).actions.reset, true);
  assert.equal(view(WORKSPACE_STATES.PRODUCTION).actions.reset, true);
});


test("reset uses a dedicated dialog instead of window confirm", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workspace-reset-dialog.js"),
  ]);
  assert.match(html, /id="workspaceResetDialog"/);
  assert.match(source, /showModal\(\)/);
  assert.doesNotMatch(source, /window\.confirm/);
});


test("text confirmation accepts only exact RIPRISTINA", () => {
  assert.equal(canConfirmWorkspaceReset("RIPRISTINA"), true);
  assert.equal(canConfirmWorkspaceReset("ripristina"), false);
  assert.equal(canConfirmWorkspaceReset(" RIPRISTINA"), false);
  assert.equal(canConfirmWorkspaceReset("RIPRISTINA "), false);
});


test("busy reset cannot be confirmed twice", () => {
  assert.equal(canConfirmWorkspaceReset("RIPRISTINA", true), false);
});


test("reset loading disables controls and reports progress", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-reset-dialog.js",
  );
  assert.match(source, /confirmation\.disabled = true/);
  assert.match(source, /cancelReset\.disabled = true/);
  assert.match(source, /Ripristino in corso/);
  assert.match(source, /aria-busy/);
});


test("successful reset invalidates every operational surface", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-lifecycle.js",
  );
  assert.match(source, /workspace:reset-completed/);
  assert.match(source, /demo:workspace-changed/);
  assert.match(source, /refreshWorkspaceStatus/);
  assert.match(source, /Workspace ripristinato/);
});


test("reset error remains in the dialog with a safe message", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-reset-dialog.js",
  );
  assert.match(source, /WORKSPACE_RESET_FAILED/);
  assert.match(source, /I dati operativi sono rimasti invariati/);
  assert.match(source, /progress\.textContent = presentation\.message/);
});


test("Nuova giornata operativa reuses the workspace reset flow", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-lifecycle.js",
  );
  assert.match(source, /action === "new-day"/);
  assert.match(
    source,
    /importAfterReset: true[\s\S]*Rimuove i dati operativi correnti/,
  );
});


test("PRODUCTION import can continue in the current workspace", () => {
  assert.equal(
    importFlowForState(WORKSPACE_STATES.PRODUCTION),
    "choose-production",
  );
});


test("PRODUCTION import can reset and continue to imports", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/workspace-reset-dialog.js"),
  ]);
  assert.match(html, /Continua nel workspace corrente/);
  assert.match(html, /Ripristina e importa/);
  assert.match(source, /importAfterReset: true/);
});


test("DEMO import requires reset before real files", () => {
  assert.equal(importFlowForState(WORKSPACE_STATES.DEMO), "reset-demo");
});


test("DEMO submit is intercepted before calling the import API", async () => {
  const source = await frontendFile(
    "assets/js/modules/import-workbook.js",
  );
  assert.match(source, /document\.body\.dataset\.workspaceState === "DEMO"/);
  assert.match(source, /workspace:import-requested/);
});


test("reset restores onboarding and clears import presentation", async () => {
  const [onboarding, importer] = await Promise.all([
    frontendFile("assets/js/modules/onboarding.js"),
    frontendFile("assets/js/modules/import-workbook.js"),
  ]);
  assert.match(onboarding, /type: "workspace-reset"/);
  assert.match(importer, /workspace:reset-completed/);
  assert.match(importer, /setStatus\(elements, "In attesa"\)/);
});


test("workspace badge refreshes only after lifecycle mutations that change it", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-lifecycle.js",
  );
  for (const eventName of [
    "operations:data-imported",
    "demo:workspace-changed",
    "fleet:registry-loaded",
    "workspace:refresh-requested",
  ]) {
    assert.match(source, new RegExp(eventName.replace(":", "\\:")));
  }
  assert.doesNotMatch(source, /briefing:changed/);
});


test("responsive lifecycle CSS covers tablet and mobile", async () => {
  const css = await frontendFile("assets/css/workspace-lifecycle.css");
  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(
    css,
    /\.workspace-menu-panel[\s\S]*position: fixed/,
  );
  assert.match(
    css,
    /\.app-header-actions[\s\S]*grid-template-columns: minmax\(0, 1\.25fr\)/,
  );
  assert.match(css, /grid-template-columns: 1fr/);
});


test("reset dialog exposes labels descriptions and live status", async () => {
  const html = await frontendFile("index.html");
  const dialog = html.match(
    /<dialog[\s\S]*?id="workspaceResetDialog"[\s\S]*?<\/dialog>/,
  )?.[0] || "";
  assert.match(dialog, /aria-labelledby="workspaceResetTitle"/);
  assert.match(dialog, /aria-describedby="workspaceResetDescription"/);
  assert.match(dialog, /aria-live="polite"/);
  assert.match(dialog, /Scrivi <strong>RIPRISTINA<\/strong>/);
  assert.match(dialog, /id="confirmWorkspaceResetBtn"[\s\S]*disabled/);
});


test("Escape is blocked only while reset is running", async () => {
  const source = await frontendFile(
    "assets/js/modules/workspace-reset-dialog.js",
  );
  assert.match(
    source,
    /resetDialog\.addEventListener\("keydown"[\s\S]*event\.key !== "Escape"[\s\S]*if \(!busy\) closeReset/,
  );
  assert.match(
    source,
    /resetDialog\.addEventListener\("cancel"[\s\S]*if \(busy\) event\.preventDefault/,
  );
  assert.match(source, /restoreFocus/);
});


test("workspace frontend has no direct business decisions or console noise", async () => {
  const paths = [
    "assets/js/modules/workspace-state.js",
    "assets/js/modules/workspace-header.js",
    "assets/js/modules/workspace-card.js",
    "assets/js/modules/workspace-reset-dialog.js",
    "assets/js/modules/workspace-lifecycle.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));
  const combined = sources.join("\n");
  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
  assert.doesNotMatch(combined, /calculateCapacity|calculateReadiness/);
  assert.doesNotMatch(combined, /fetch\(/);
});


test("API client uses only the two versioned workspace endpoints", async () => {
  const source = await frontendFile("assets/js/api.js");
  assert.match(source, /\/api\/workspace\/v1\/status/);
  assert.match(source, /\/api\/workspace\/v1\/reset/);
  assert.doesNotMatch(source, /\/api\/workspace\/v1\/new-day/);
});

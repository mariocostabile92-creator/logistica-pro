import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  PLANNING_WORKSPACE_STATES,
} from "../assets/js/modules/planning-workspace/models.js";
import {
  applyPlanningWorkspaceEvent,
  createPlanningWorkspaceState,
  derivePlanningWorkspaceView,
} from "../assets/js/modules/planning-workspace/state.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


test("Planning Workspace starts in an explicit loading state", () => {
  const state = createPlanningWorkspaceState({ planningDate: "2026-07-22" });
  const view = derivePlanningWorkspaceView(state);

  assert.equal(state.state, PLANNING_WORKSPACE_STATES.LOADING);
  assert.equal(view.loading, true);
  assert.equal(view.statusTitle, "Preparazione Planning Workspace");
});


test("state accepts every declared presentation without deriving decisions", () => {
  const events = new Map([
    ["empty-detected", PLANNING_WORKSPACE_STATES.EMPTY],
    ["ready-received", PLANNING_WORKSPACE_STATES.READY],
    ["warning-received", PLANNING_WORKSPACE_STATES.WARNING],
    ["load-failed", PLANNING_WORKSPACE_STATES.ERROR],
    ["legacy-active", PLANNING_WORKSPACE_STATES.LEGACY],
  ]);
  for (const [eventType, expected] of events) {
    const current = createPlanningWorkspaceState();
    const next = applyPlanningWorkspaceEvent(current, { type: eventType });
    assert.equal(next.state, expected);
  }
});


test("legacy state names the disconnected Runtime and preserves placeholders", () => {
  const state = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    { type: "legacy-active" },
  );
  const view = derivePlanningWorkspaceView(state);

  assert.equal(view.badge, "Legacy");
  assert.equal(view.statusDescription, "Planning Runtime non ancora collegato.");
  assert.equal(view.readiness.value, "Non disponibile");
  assert.equal(view.conflicts.value, "Non disponibili");
  assert.equal(view.draft.detail, "Draft disponibile nelle prossime fasi.");
  assert.equal(view.publication.detail, "Publication non disponibile.");
  assert.equal(view.canConfirm, false);
});


test("ready and warning views present only values explicitly supplied", () => {
  const snapshot = {
    readiness: { value: "Verificata", detail: "Contratto esplicito" },
    conflicts: { value: "2", detail: "Contratto esplicito" },
    canConfirm: true,
  };
  const ready = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    { type: "ready-received", snapshot },
  );
  const warning = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    { type: "warning-received", snapshot },
  );

  assert.equal(derivePlanningWorkspaceView(ready).readiness.value, "Verificata");
  assert.equal(derivePlanningWorkspaceView(ready).canConfirm, true);
  assert.equal(derivePlanningWorkspaceView(warning).tone, "attention");
});


test("layout preserves the definitive desktop component hierarchy", async () => {
  const source = await frontendFile(
    "assets/js/modules/planning-workspace/layout.js",
  );
  const expectedOrder = [
    "createPlanningHeader()",
    "createStatusCard()",
    "createReadinessCard()",
    "createConflictSummary()",
    "createTimelinePlaceholder()",
    "createDraftPlaceholder()",
    "createPublicationPlaceholder()",
    "createFooterActions()",
  ];
  let previous = -1;
  for (const marker of expectedOrder) {
    const current = source.indexOf(marker, previous + 1);
    assert.ok(current > previous, `${marker} must preserve layout order`);
    previous = current;
  }
});


test("renderer covers all components and exposes loading semantics", async () => {
  const [renderer, components] = await Promise.all([
    frontendFile("assets/js/modules/planning-workspace/renderer.js"),
    frontendFile("assets/js/modules/planning-workspace/components.js"),
  ]);

  assert.match(renderer, /aria-busy/);
  for (const component of [
    "status",
    "readiness",
    "conflicts",
    "timeline",
    "draft",
    "publication",
    "actions",
  ]) {
    assert.match(components, new RegExp(`planning-${component}|${component}`));
  }
  assert.match(components, /role: "status"/);
  assert.match(components, /aria-labelledby/);
});


test("responsive styles cover tablet mobile order and horizontal containment", async () => {
  const css = await frontendFile("assets/css/planning-workspace.css");

  assert.match(css, /overflow: clip/);
  assert.match(css, /min-width: 0/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /data-active-workspace="operations"[\s\S]*workspace-tab\.active/);
  assert.match(
    css,
    /planning-workspace-draft[\s\S]*?order: 4[\s\S]*?planning-workspace-timeline[\s\S]*?order: 5/,
  );
  assert.match(css, /prefers-reduced-motion/);
});


test("keyboard navigation supports arrows boundaries and Escape", async () => {
  const source = await frontendFile(
    "assets/js/modules/planning-workspace/index.js",
  );

  for (const key of ["ArrowLeft", "ArrowRight", "Home", "End", "Escape"]) {
    assert.match(source, new RegExp(`"${key}"`));
  }
  assert.match(source, /focusRelativeAction/);
  assert.match(source, /legacyButton\.focus/);
});


test("Planning Workspace is isolated from APIs Runtime and business algorithms", async () => {
  const paths = [
    "assets/js/modules/planning-workspace/index.js",
    "assets/js/modules/planning-workspace/models.js",
    "assets/js/modules/planning-workspace/state.js",
    "assets/js/modules/planning-workspace/renderer.js",
    "assets/js/modules/planning-workspace/layout.js",
    "assets/js/modules/planning-workspace/components.js",
    "assets/js/modules/planning-workspace/utils.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));
  const combined = sources.join("\n");

  assert.doesNotMatch(combined, /api\.js|fetch\(|getLatestPlanning/);
  assert.doesNotMatch(combined, /PlanningInputRuntime|generatePlanning/);
  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
});


test("Operations exposes Planning Workspace before the closed legacy flow", async () => {
  const [html, navigation, loader] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/view-navigation.js"),
    frontendFile("assets/js/modules/workspace-loader.js"),
  ]);
  const workspace = html.indexOf('id="planningWorkspaceSection"');
  const legacy = html.indexOf('id="legacyOperationsRegion"');

  assert.ok(workspace > 0);
  assert.ok(legacy > workspace);
  assert.match(navigation, /"planningWorkspaceSection"/);
  assert.match(navigation, /"legacyOperationsRegion"/);
  assert.match(loader, /import\("\.\/planning-workspace\/index\.js"\)/);
  assert.match(loader, /planningWorkspace\.initPlanningWorkspace\(\)/);
});

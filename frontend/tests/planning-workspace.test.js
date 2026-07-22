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
import {
  createPlanningReadinessLoader,
  normalizePlanningReadiness,
  readinessEventType,
} from "../assets/js/modules/planning-workspace/readiness.js";
import {
  createPlanningConflictLoader,
  normalizePlanningConflictResult,
} from "../assets/js/modules/planning-workspace/conflicts.js";


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
    ["blocked-received", PLANNING_WORKSPACE_STATES.BLOCKED],
    ["stale-received", PLANNING_WORKSPACE_STATES.STALE],
    ["partial-received", PLANNING_WORKSPACE_STATES.PARTIAL],
    ["missing-received", PLANNING_WORKSPACE_STATES.MISSING],
    ["invalid-received", PLANNING_WORKSPACE_STATES.INVALID],
    ["incompatible-received", PLANNING_WORKSPACE_STATES.INCOMPATIBLE],
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
  assert.equal(view.conflicts, null);
  assert.equal(view.draft.detail, "Draft disponibile nelle prossime fasi.");
  assert.equal(view.publication.detail, "Publication non disponibile.");
  assert.equal(view.canConfirm, false);
});


test("ready and warning views present only values explicitly supplied", () => {
  const readiness = {
    status: "READY",
    score: 100,
    isReady: true,
    rationale: "Contratto esplicito",
    blockers: [],
    warnings: [],
    conflicts: { value: "2", detail: "Contratto esplicito" },
  };
  const snapshot = { readiness };
  const ready = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    { type: "ready-received", snapshot },
  );
  const warning = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    { type: "warning-received", snapshot },
  );

  assert.equal(derivePlanningWorkspaceView(ready).readiness.value, "100/100 · Pronto");
  assert.equal(derivePlanningWorkspaceView(ready).canConfirm, false);
  assert.equal(derivePlanningWorkspaceView(warning).tone, "attention");
});


function readinessPayload(status = "READY") {
  return {
    status,
    score: { value: status === "READY" ? 100 : 72 },
    is_ready: ["READY", "WARNING"].includes(status),
    blockers: status === "BLOCKED"
      ? [{
        code: "FLEET_AVAILABLE",
        message: "Nessun Asset risulta disponibile.",
        remediation_hint: "Verifica Fleet.",
        source: "fleet",
      }]
      : [],
    warnings: status === "WARNING"
      ? [{
        code: "FLEET_CAPABILITIES",
        message: "Capability Fleet incomplete.",
        remediation_hint: "Completa le capability.",
        source: "fleet",
      }]
      : [],
    missing_inputs: [],
    rationale: "Valutazione prodotta dal backend.",
    evaluated_at: "2026-07-22T07:00:00Z",
    operational_unit: {
      external_identifier: "unit-a",
      name: "Unit A",
    },
    planning_date: "2026-07-22",
    envelope_version: status === "READY" ? "version-1" : null,
    legacy_flow_active: true,
  };
}


function conflictPayload({ status = "READY", conflicts = [], groups = [] } = {}) {
  const blocking = conflicts.filter((item) => item.blocking).length;
  return {
    readiness: readinessPayload(status),
    report: {
      total_conflicts: conflicts.length,
      total_blocking: blocking,
      total_warnings: conflicts.length - blocking,
      groups,
      conflicts,
      timestamp: "2026-07-22T07:00:00Z",
      planning_version: "version-1",
      planning_date: "2026-07-22",
      operational_unit: {
        external_identifier: "unit-a",
        name: "Unit A",
      },
    },
  };
}


function conflict({
  id = "conflict-1",
  code = "FLEET_MISSING",
  category = "FLEET",
  severity = "CRITICAL",
  blocking = true,
} = {}) {
  return {
    id,
    code,
    category,
    severity,
    title: "Fleet non disponibile",
    description: "Lo snapshot Fleet non e disponibile.",
    source: "fleet",
    blocking,
    affected_entities: [],
    diagnostics: [{ code, message: "Missing", source: "fleet", details: [] }],
    suggestion: {
      action: "Apri Fleet e aggiorna il parco mezzi operativo.",
      workspace: "Fleet",
      rationale: "Il piano richiede Asset osservati.",
    },
    documentation_reference: "inventory#readiness",
    timestamp: "2026-07-22T07:00:00Z",
  };
}


test("readiness payload normalization supports every backend state", () => {
  for (const status of [
    "READY",
    "WARNING",
    "BLOCKED",
    "STALE",
    "PARTIAL",
    "MISSING",
    "INVALID",
    "INCOMPATIBLE",
    "LEGACY",
  ]) {
    const normalized = normalizePlanningReadiness(readinessPayload(status));
    assert.equal(normalized.status, status);
    assert.equal(
      readinessEventType(status),
      `${status.toLowerCase()}-received`,
    );
    assert.equal(normalized.operationalUnit, "Unit A");
  }
});


test("readiness normalization renders score blocker and warning without invented data", () => {
  const blocked = normalizePlanningReadiness(readinessPayload("BLOCKED"));
  const warning = normalizePlanningReadiness(readinessPayload("WARNING"));

  assert.equal(blocked.score, 72);
  assert.equal(blocked.blockers[0].code, "FLEET_AVAILABLE");
  assert.equal(warning.warnings[0].remediationHint, "Completa le capability.");
  assert.equal(blocked.envelopeVersion, null);
  assert.throws(
    () => normalizePlanningReadiness({ status: "READY" }),
    /Score readiness non valido/,
  );
});


test("readiness loader coalesces duplicate calls and allows a controlled retry", async () => {
  let calls = 0;
  let release;
  const loader = createPlanningReadinessLoader(() => {
    calls += 1;
    if (calls > 1) return Promise.resolve(readinessPayload());
    return new Promise((resolve) => { release = resolve; });
  });
  const first = loader.load();
  const duplicate = loader.load();

  assert.equal(calls, 1);
  assert.equal(first, duplicate);
  release(readinessPayload());
  await first;
  await loader.load();
  assert.equal(calls, 2);
});


test("Conflict Review normalizes empty warning and critical states", () => {
  const empty = normalizePlanningConflictResult(conflictPayload());
  const warningItem = conflict({
    id: "warning-1",
    code: "FLEET_CAPABILITIES_MISSING",
    category: "CAPABILITY",
    severity: "MEDIUM",
    blocking: false,
  });
  const warning = normalizePlanningConflictResult(conflictPayload({
    status: "WARNING",
    conflicts: [warningItem],
    groups: [{
      category: "CAPABILITY",
      label: "Capability",
      total_conflicts: 1,
      total_blocking: 0,
      highest_severity: "MEDIUM",
      conflict_ids: ["warning-1"],
    }],
  }));
  const critical = normalizePlanningConflictResult(conflictPayload({
    status: "BLOCKED",
    conflicts: [conflict()],
    groups: [{
      category: "FLEET",
      label: "Fleet",
      total_conflicts: 1,
      total_blocking: 1,
      highest_severity: "CRITICAL",
      conflict_ids: ["conflict-1"],
    }],
  }));

  assert.equal(empty.conflicts.totalConflicts, 0);
  assert.equal(warning.conflicts.totalWarnings, 1);
  assert.equal(warning.conflicts.topConflicts[0].severity, "MEDIUM");
  assert.equal(critical.conflicts.totalBlocking, 1);
  assert.equal(critical.conflicts.groups[0].category, "FLEET");
});


test("Conflict Review loader prevents duplicate requests and supports retry", async () => {
  let calls = 0;
  let release;
  const loader = createPlanningConflictLoader(() => {
    calls += 1;
    if (calls > 1) return Promise.resolve(conflictPayload());
    return new Promise((resolve) => { release = resolve; });
  });
  const first = loader.load();
  const duplicate = loader.load();

  assert.equal(first, duplicate);
  assert.equal(calls, 1);
  release(conflictPayload());
  await first;
  await loader.load();
  assert.equal(calls, 2);
});


test("state exposes backend conflict groups without deriving decisions", () => {
  const normalized = normalizePlanningConflictResult(conflictPayload({
    status: "BLOCKED",
    conflicts: [conflict()],
    groups: [{
      category: "FLEET",
      label: "Fleet",
      total_conflicts: 1,
      total_blocking: 1,
      highest_severity: "CRITICAL",
      conflict_ids: ["conflict-1"],
    }],
  }));
  const state = applyPlanningWorkspaceEvent(
    createPlanningWorkspaceState(),
    {
      type: "blocked-received",
      snapshot: normalized,
    },
  );

  assert.equal(derivePlanningWorkspaceView(state).conflicts.totalBlocking, 1);
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
  assert.match(components, /retry-conflicts/);
  assert.match(components, /readiness-blocker-list/);
  assert.match(components, /readiness-warning-list/);
  assert.match(components, /conflict-groups/);
  assert.match(components, /conflict-list/);
  assert.match(components, /aria-live/);
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
  assert.match(css, /planning-conflict-group summary:focus-visible/);
  assert.match(css, /planning-conflict-counts[\s\S]*grid-template-columns: 1fr/);
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


test("Planning Workspace consumes one Conflict Review API and no business algorithms", async () => {
  const paths = [
    "assets/js/modules/planning-workspace/index.js",
    "assets/js/modules/planning-workspace/models.js",
    "assets/js/modules/planning-workspace/state.js",
    "assets/js/modules/planning-workspace/renderer.js",
    "assets/js/modules/planning-workspace/layout.js",
    "assets/js/modules/planning-workspace/components.js",
    "assets/js/modules/planning-workspace/utils.js",
    "assets/js/modules/planning-workspace/readiness.js",
    "assets/js/modules/planning-workspace/conflicts.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));
  const combined = sources.join("\n");

  assert.match(combined, /getPlanningConflicts/);
  assert.doesNotMatch(combined, /getPlanningReadiness/);
  assert.doesNotMatch(combined, /fetch\(|getLatestPlanning/);
  assert.doesNotMatch(combined, /PlanningInputRuntime|generatePlanning/);
  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
});


test("frontend exposes loading error retry and one initial conflict request", async () => {
  const [index, api, renderer] = await Promise.all([
    frontendFile("assets/js/modules/planning-workspace/index.js"),
    frontendFile("assets/js/api.js"),
    frontendFile("assets/js/modules/planning-workspace/renderer.js"),
  ]);

  assert.match(index, /type: "load-started"/);
  assert.match(index, /type: "load-failed"/);
  assert.match(index, /retry-conflicts/);
  assert.match(index, /createPlanningConflictLoader/);
  assert.match(api, /\/api\/planning\/conflicts/);
  assert.match(api, /signal/);
  assert.match(renderer, /retryButton\.hidden/);
  assert.match(renderer, /createElement|element\("details"/);
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

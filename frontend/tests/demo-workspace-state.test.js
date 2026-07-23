import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyDemoWorkspaceEvent,
  createDemoWorkspaceState,
  deriveDemoWorkspaceView,
} from "../assets/js/modules/demo-workspace-state.js";


const summary = {
  dataset_version: "demo_dataset_v1",
  created_at: "2099-01-15T08:00:00Z",
  planning_id: 41,
  planning_status: "ready",
  counts: {
    tasks: 10,
    human_resources: 12,
    assets: 11,
    warnings: 3,
  },
};


test("demo card starts in a clear loading state", () => {
  const view = deriveDemoWorkspaceView(createDemoWorkspaceState());

  assert.equal(view.hidden, false);
  assert.equal(view.loading, true);
  assert.equal(view.active, false);
  assert.equal(view.statusMessage, "");
});


test("disabled demo support hides every demo surface", () => {
  const current = applyDemoWorkspaceEvent(
    createDemoWorkspaceState(),
    { type: "disabled" },
  );

  assert.equal(deriveDemoWorkspaceView(current).hidden, true);
});


test("loaded demo exposes active state and persisted summary", () => {
  let current = createDemoWorkspaceState();
  current = applyDemoWorkspaceEvent(current, {
    type: "operation-started",
  });
  assert.equal(deriveDemoWorkspaceView(current).loading, true);

  current = applyDemoWorkspaceEvent(current, {
    type: "load-completed",
    summary,
  });
  const view = deriveDemoWorkspaceView(current);

  assert.equal(view.active, true);
  assert.equal(view.badge, "Modalit\u00e0 demo attiva");
  assert.equal(view.summary.planning_id, 41);
});


test("reset returns the card to the initial onboarding action", () => {
  let current = createDemoWorkspaceState({
    initialized: true,
    enabled: true,
    status: "ready",
    summary,
  });
  current = applyDemoWorkspaceEvent(current, {
    type: "reset-completed",
  });
  const view = deriveDemoWorkspaceView(current);

  assert.equal(view.active, false);
  assert.equal(view.inactive, true);
  assert.equal(view.loadLabel, "Carica demo");
  assert.match(view.statusMessage, /rimossi/);
});


test("controlled failures remain actionable presentation state", () => {
  const current = applyDemoWorkspaceEvent(
    createDemoWorkspaceState(),
    {
      type: "operation-failed",
      message: "Il workspace demo non e stato caricato.",
    },
  );
  const view = deriveDemoWorkspaceView(current);

  assert.equal(view.loading, false);
  assert.equal(view.inactive, true);
  assert.equal(view.loadLabel, "Riprova caricamento");
  assert.equal(
    view.statusMessage,
    "Il workspace demo non e stato caricato.",
  );
});


test("page contains demo controls and accessible reset confirmation", async () => {
  const html = await readFile(
    new URL("../index.html", import.meta.url),
    "utf8",
  );

  assert.match(html, /Prova con dati demo/);
  assert.match(
    html,
    /Carica un ambiente sintetico e prova l'intero flusso senza usare dati reali\./,
  );
  assert.match(html, /Carica demo/);
  assert.match(html, /Apri Planning/);
  assert.match(html, /Apri Fleet/);
  assert.match(html, /Esporta CSV/);
  assert.match(html, /Ripristina workspace/);
  assert.match(
    html,
    /Questa operazione rimuover&agrave; tutti i dati operativi correnti/,
  );
  assert.match(html, /<dialog[\s\S]*id="workspaceResetDialog"/);
});


test("demo module reuses navigation and export without window confirm", async () => {
  const source = await readFile(
    new URL(
      "../assets/js/modules/demo-workspace.js",
      import.meta.url,
    ),
    "utf8",
  );
  const css = await readFile(
    new URL(
      "../assets/css/demo-workspace.css",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(source, /downloadPlanningCsv/);
  assert.match(source, /workspace:navigate/);
  assert.match(source, /workspace:reset-requested/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.doesNotMatch(source, /console\.(error|warn)/);
  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
});

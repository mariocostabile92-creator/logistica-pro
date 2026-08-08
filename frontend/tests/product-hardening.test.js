import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("administrative first paint contains only the definitive Home surface", async () => {
  const html = await source("index.html");
  assert.match(html, /id="appBootstrapShell"/);
  assert.match(html, /<header class="app-header" hidden>/);
  assert.match(html, /<main class="app-shell" hidden>/);
  for (const id of [
    "legacyMissionControlSection", "workspaceCurrentSection",
    "onboardingSection", "briefingSection", "demoWorkspaceHomeSection",
  ]) {
    assert.doesNotMatch(html, new RegExp(`id="${id}"`));
  }
  assert.equal(html.match(/id="missionControlSection"/g)?.length, 1);
});

test("bootstrap reveals the initialized app atomically and provides a finite error state", async () => {
  const app = await source("assets/js/app.js");
  const bootstrap = await source("assets/js/modules/app-bootstrap.js");
  assert.match(app, /await requireAdministrativeSession\(\)[\s\S]*const homeReady = initMissionControl\(\)[\s\S]*initViewNavigation[\s\S]*await homeReady;[\s\S]*revealAdministrativeApp\(\)/);
  assert.doesNotMatch(bootstrap, /await frame\(\)|requestAnimationFrame/);
  assert.match(bootstrap, /header\.hidden = false[\s\S]*main\.hidden = false[\s\S]*shell\.hidden = true/);
  assert.match(bootstrap, /dataset\.appState = "failed"/);
  assert.doesNotMatch(bootstrap, /setTimeout|opacity/);
});

test("Fleet-only styles are lazy and never block the Home shell", async () => {
  const html = await source("index.html");
  const loader = await source("assets/js/modules/workspace-loader.js");
  for (const stylesheet of [
    "documents-workspace.css", "journal-control-room.css",
    "attachments.css", "fleet-vision-workspace.css",
  ]) {
    assert.doesNotMatch(html, new RegExp(`stylesheet[^>]+${stylesheet}`));
    assert.match(loader, new RegExp(stylesheet.replace(".", "\\.")));
  }
});

test("retirement worker removes PWA caches and never intercepts application traffic", async () => {
  const [html, manifestText, worker, registration] = await Promise.all([
    source("index.html"), source("manifest.webmanifest"), source("sw.js"),
    source("assets/js/modules/pwa.js"),
  ]);
  const manifest = JSON.parse(manifestText);
  assert.equal(manifest.start_url, "/app/");
  assert.equal(manifest.display, "standalone");
  assert.match(html, /rel="manifest"/);
  assert.match(worker, /CACHE_PREFIX = "operations-"/);
  assert.match(worker, /caches\.delete/);
  assert.match(worker, /registration\.unregister/);
  assert.doesNotMatch(worker, /addEventListener\("fetch"|respondWith|cache\.add/);
  assert.match(registration, /updateViaCache: "none"/);
  assert.match(registration, /sw\.js\?v=3/);
  assert.match(registration, /getRegistrations\(\)/);
});

test("bootstrap defers PWA retirement until Home data settles", async () => {
  const app = await source("assets/js/app.js");
  assert.match(app, /retirePwaAfterHome\(homeReady\)/);
  assert.match(app, /Promise\.resolve\(homeReady\)\.finally/);
  assert.doesNotMatch(app, /initBriefing|registerServiceWorker/);
});

test("workspace first paints await only their current primary surface", async () => {
  const loader = await source("assets/js/modules/workspace-loader.js");
  const operations = loader.slice(loader.indexOf("operations: async"), loader.indexOf("workforce: async"));
  const workforce = loader.slice(loader.indexOf("workforce: async"), loader.indexOf("fleet: async"));
  const fleet = loader.slice(loader.indexOf("fleet: async"), loader.indexOf("settings: async"));
  assert.match(operations, /planning-workspace\/index\.js/);
  assert.doesNotMatch(operations, /import-planning|import-fleet|operations-dashboard|onboarding/);
  assert.match(loader, /operations-legacy-trigger/);
  assert.match(loader, /if \(disclosure\.open\) void prepareLegacyOperations\(\)/);
  assert.doesNotMatch(operations, /void prepareLegacyOperations\(\)/);
  assert.match(operations, /return async \(\)[\s\S]*await planningWorkspace\.initPlanningWorkspace\(\)/);
  assert.match(workforce, /return async \(\)[\s\S]*module\.initWorkforcePage\(\)[\s\S]*await module\.prepareWorkforceFirstPaint\(\)/);
  assert.match(fleet, /loadWorkspaceStyles\("fleet"\)/);
  assert.match(fleet, /requestIdleCallback\(loadSecondaryStyles\)/);
  assert.match(fleet, /await module\.prepareFleetFirstPaint\(\)/);
});

test("Planning and Workforce expose finite first-paint promises", async () => {
  const [planning, operations, layout, workforce] = await Promise.all([
    source("assets/js/modules/planning-workspace/index.js"),
    source("assets/js/modules/planning-operations/index.js"),
    source("assets/js/modules/planning-workspace/layout.js"),
    source("assets/js/modules/workforce-page.js"),
  ]);
  assert.match(operations, /initialLoadPromise = load\(\);[\s\S]*return initialLoadPromise;/);
  assert.match(layout, /const operationsReady = initPlanningOperations\(operations\)/);
  assert.match(planning, /firstPaintPromise = Promise\.resolve\(refs\.operationsReady\)/);
  assert.match(workforce, /export function prepareWorkforceFirstPaint\(\)[\s\S]*firstPaintPromise = refresh\(\)\.finally/);
});

test("source files do not contain common UTF-8 mojibake sequences", async () => {
  const paths = [
    "index.html", "assets/js/app.js", "assets/js/modules/app-bootstrap.js",
    "manifest.webmanifest", "offline.html",
  ];
  for (const path of paths) {
    assert.doesNotMatch(await source(path), /â€”|â€™|Ã¨|Ã |Â/);
  }
});

test("Planning failure state is finite, retryable and never injects a raw API error", async () => {
  const module = await source("assets/js/modules/planning-operations/index.js");
  assert.match(module, /role="alert"/);
  assert.match(module, /data-planning-retry/);
  assert.match(module, /userMessageForError/);
  assert.match(module, /data-planning-error/);
  assert.doesNotMatch(module, /<p>\$\{error/);
});

test("lazy Planning styles preserve the global mobile navigation grid", async () => {
  const css = await source("assets/css/planning-workspace.css");
  const mobile = css.slice(css.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /data-active-workspace="operations"[\s\S]*workspace-tabs[\s\S]*repeat\(3, minmax\(0, 1fr\)\)/);
});

test("bootstrap and SPA navigation expose measured shell and useful-content timings", async () => {
  const [bootstrap, navigation, mission] = await Promise.all([
    source("assets/js/modules/app-bootstrap.js"),
    source("assets/js/modules/view-navigation.js"),
    source("assets/js/modules/mission-control.js"),
  ]);
  assert.match(bootstrap, /dataset\.shellReadyMs/);
  assert.match(navigation, /dataset\.navigationReadyMs/);
  assert.match(navigation, /dataset\.navigationReadyView/);
  assert.match(navigation, /dataset\.navigationFeedbackMs/);
  assert.match(mission, /dataset\.homeUsefulMs/);
});

test("an expired API session triggers one coherent redirect instead of partial workspace errors", async () => {
  const [api, session] = await Promise.all([
    source("assets/js/api.js"), source("assets/js/auth/session.js"),
  ]);
  assert.match(api, /response\.status === 401[\s\S]*auth:expired/);
  assert.match(session, /sessionRedirecting/);
  assert.match(session, /addEventListener\("auth:expired", redirectToLogin\)/);
});

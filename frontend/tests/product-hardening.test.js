import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("administrative first paint is neutral and legacy sources are statically hidden", async () => {
  const html = await source("index.html");
  assert.match(html, /id="appBootstrapShell"/);
  assert.match(html, /<header class="app-header" hidden>/);
  assert.match(html, /<main class="app-shell" hidden>/);
  for (const id of [
    "legacyMissionControlSection", "workspaceCurrentSection",
    "onboardingSection", "demoWorkspaceHomeSection",
  ]) {
    const section = html.slice(html.indexOf(`id="${id}"`), html.indexOf(">", html.indexOf(`id="${id}"`)));
    assert.match(section, /\bhidden\b/);
  }
});

test("bootstrap reveals the initialized app atomically and provides a finite error state", async () => {
  const app = await source("assets/js/app.js");
  const bootstrap = await source("assets/js/modules/app-bootstrap.js");
  assert.match(app, /await requireAdministrativeSession\(\)[\s\S]*initMissionControl\(\)[\s\S]*initViewNavigation[\s\S]*await revealAdministrativeApp\(\)/);
  assert.match(bootstrap, /await frame\(\)/);
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

test("PWA is network-first, caches only the offline page and versions its cache", async () => {
  const [html, manifestText, worker, registration] = await Promise.all([
    source("index.html"), source("manifest.webmanifest"), source("sw.js"),
    source("assets/js/modules/pwa.js"),
  ]);
  const manifest = JSON.parse(manifestText);
  assert.equal(manifest.start_url, "/app/");
  assert.equal(manifest.display, "standalone");
  assert.match(html, /rel="manifest"/);
  assert.match(worker, /operations-offline-v1/);
  assert.match(worker, /request\.mode !== "navigate"/);
  assert.match(worker, /fetch\(request\)\.catch/);
  assert.doesNotMatch(worker, /cache\.addAll|respondWith\(caches\.match\(request\)/);
  assert.match(registration, /updateViaCache: "none"/);
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

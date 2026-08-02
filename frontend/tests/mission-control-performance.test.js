import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { applyBriefingEvent } from "../assets/js/modules/briefing-state.js";
import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "../assets/js/modules/mission-control-state.js";
import { createSnapshotCache } from "../assets/js/utils/snapshot-cache.js";


const frontendUrl = new URL("../", import.meta.url);


async function frontendFile(path) {
  return readFile(new URL(path, frontendUrl), "utf8");
}


test("snapshot cache reuses a valid response without a duplicate request", async () => {
  const cache = createSnapshotCache({ ttlMs: 1000 });
  let calls = 0;
  const loader = async () => ({ version: ++calls });
  const first = await cache.read(loader);
  const second = await cache.read(loader);
  assert.equal(calls, 1);
  assert.equal(first.fromCache, false);
  assert.equal(second.fromCache, true);
  assert.deepEqual(second.value, first.value);
});


test("concurrent snapshot reads share the same in-flight request", async () => {
  const cache = createSnapshotCache();
  let calls = 0;
  let resolveRequest;
  const loader = () => {
    calls += 1;
    return new Promise((resolve) => { resolveRequest = resolve; });
  };
  const first = cache.read(loader);
  const second = cache.read(loader);
  resolveRequest({ status: "ready" });
  assert.deepEqual(await first, await second);
  assert.equal(calls, 1);
});


test("forced refresh aborts an obsolete request and stores the new response", async () => {
  const cache = createSnapshotCache();
  const stale = cache.read(({ signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(
      new DOMException("aborted", "AbortError"),
    ));
  }));
  const fresh = cache.read(async () => ({ version: 2 }), { force: true });
  await assert.rejects(stale, { name: "AbortError" });
  assert.deepEqual((await fresh).value, { version: 2 });
  assert.equal(cache.peek().fresh, true);
});


test("refresh keeps an existing briefing available while data is in flight", () => {
  const briefing = { status: "available", executive_summary: "Corrente" };
  const current = {
    phase: "available",
    briefing,
    filter: "all",
    expanded: false,
    error: null,
    demoEnabled: false,
  };
  const next = applyBriefingEvent(current, { type: "load-started" });
  assert.equal(next.phase, "available");
  assert.equal(next.briefing, briefing);
});


test("one source failure does not block the parallel Home summary", async () => {
  const api = await frontendFile("assets/js/modules/mission-control-api.js");
  assert.match(api, /Promise\.allSettled/);
  assert.match(api, /partial: failedSources > 0/);
  assert.match(api, /listFleetAssets\(\)/);
  assert.doesNotMatch(api, /getLatestPlanning/);
  assert.doesNotMatch(api, /getFleetVision/);
});


test("non-visible workspaces are loaded dynamically instead of at startup", async () => {
  const [app, loader, html] = await Promise.all([
    frontendFile("assets/js/app.js"),
    frontendFile("assets/js/modules/workspace-loader.js"),
    frontendFile("index.html"),
  ]);
  assert.doesNotMatch(app, /from "\.\/modules\/(fleet-page|workforce-page|planning-page)/);
  assert.match(loader, /import\("\.\/fleet-page\.js(?:\?v=\d+)?"\)/);
  assert.match(loader, /import\("\.\/workforce-page\.js(?:\?v=\d+)?"\)/);
  assert.match(loader, /prepared\.has\(view\)/);
  assert.match(loader, /loadWorkspaceStyles/);
  assert.doesNotMatch(html, /href="\.\/assets\/css\/workforce\.css/);
  assert.doesNotMatch(html, /href="\.\/assets\/css\/fleet\.css/);
});


test("Home renderer is componentized instead of one large controller", async () => {
  const [controller, renderer] = await Promise.all([
    frontendFile("assets/js/modules/mission-control.js"),
    frontendFile("assets/js/modules/mission-control/renderer.js"),
  ]);
  assert.match(controller, /loadMissionControlSummary/);
  assert.match(controller, /renderMissionControl/);
  assert.match(renderer, /renderHero/);
  assert.match(renderer, /renderPriorities/);
  assert.match(renderer, /renderRecent/);
});


test("Home shell renders before background summary requests", async () => {
  const mission = await frontendFile("assets/js/modules/mission-control.js");
  assert.match(mission, /renderMissionControl\(deriveMissionControlView\(state\)\);[\s\S]*refreshSummary\(\)/);
  assert.doesNotMatch(mission, /await loadMissionControlSummary/);
});


test("navigation aborts an obsolete Briefing request", async () => {
  const briefing = await frontendFile("assets/js/modules/briefing.js");
  assert.match(briefing, /workspace:view-started/);
  assert.match(briefing, /briefingSnapshotCache\.abort\(\)/);
  assert.match(briefing, /isAbortError/);
});


test("Mission and workspace listeners are guarded against duplicate setup", async () => {
  const [mission, workspace, loader] = await Promise.all([
    frontendFile("assets/js/modules/mission-control.js"),
    frontendFile("assets/js/modules/workspace-lifecycle.js"),
    frontendFile("assets/js/modules/workspace-loader.js"),
  ]);
  for (const source of [mission, workspace, loader]) {
    assert.match(source, /if \(initialized|if \(loaderInitialized/);
  }
});


test("operational changes coalesce Home refreshes", async () => {
  const mission = await frontendFile("assets/js/modules/mission-control.js");
  assert.match(mission, /refreshQueued/);
  assert.match(mission, /damage:changed/);
  assert.match(mission, /maintenance:changed/);
  assert.match(mission, /documents:changed/);
});

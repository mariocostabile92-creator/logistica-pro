import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { filteredRoutes } from "../assets/js/modules/planning-operations/state.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const source = (relative) => readFile(path.join(FRONTEND, relative), "utf8");


test("Planning operations is split into dedicated operational components", async () => {
  const files = await Promise.all([
    "api.js", "state.js", "hero.js", "kpi.js", "forecast.js", "routes.js",
    "renderer.js", "index.js",
  ].map((name) => source(`assets/js/modules/planning-operations/${name}`)));
  assert.equal(files.length, 8);
  assert.ok(files.every((content) => content.length > 100));
});


test("route filters are deterministic and never invent assignments", () => {
  const routes = [
    { route_id: "R1", driver_id: null, plate: "AA1", complete: false, conflicts: [] },
    { route_id: "R2", driver_id: "D2", plate: null, complete: false, conflicts: [{ severity: "critical" }] },
    { route_id: "R3", driver_id: "D3", plate: "AA3", complete: true, conflicts: [] },
  ];
  assert.deepEqual(filteredRoutes({ payload: { routes }, query: "", filter: "missing-driver" }).map((item) => item.route_id), ["R1"]);
  assert.deepEqual(filteredRoutes({ payload: { routes }, query: "", filter: "missing-vehicle" }).map((item) => item.route_id), ["R2"]);
  assert.deepEqual(filteredRoutes({ payload: { routes }, query: "", filter: "conflict" }).map((item) => item.route_id), ["R2"]);
});


test("operational API reuses import assignment and lifecycle contracts", async () => {
  const api = await source("assets/js/modules/planning-operations/api.js");
  assert.match(api, /previewImport/);
  assert.match(api, /patchPlanningAssignment/);
  assert.match(api, /patchPlanningConvocation/);
  assert.match(api, /transitionOperationalPlanning/);
  assert.doesNotMatch(api, /fetch\s*\(/);
});


test("advanced diagnostics is lazy and administrator-gated", async () => {
  const workspace = await source("assets/js/modules/planning-workspace/index.js");
  const operations = await source("assets/js/modules/planning-operations/index.js");
  assert.match(workspace, /diagnostics\.open/);
  assert.match(workspace, /loadConflictReview\(\)/);
  assert.match(operations, /permissions\.diagnostics/);
});


test("Planning operations covers desktop tablet and mobile without fixed canvas", async () => {
  const css = await source("assets/css/planning-workspace.css");
  assert.match(css, /planning-route-card/);
  assert.match(css, /@media \(max-width: 1000px\)/);
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.doesNotMatch(css, /\.planning-operations[^}]*width:\s*\d{4}px/s);
});

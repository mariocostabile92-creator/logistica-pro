import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Scadenziario workspace is removed while Fleet Vision owns deadline monitoring", async () => {
  const [page, fleet, vision, sections, renderer, navigation] = await Promise.all([
    file("index.html"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/fleet-vision-workspace.js"),
    file("assets/js/modules/fleet-vision/sections.js"),
    file("assets/js/modules/fleet-vision/renderer.js"),
    file("assets/js/modules/fleet-vision/navigation.js"),
  ]);

  assert.doesNotMatch(page, /data-fleet-module="deadlines"|id="deadlinesWorkspace"|deadlines-workspace\.css|Scadenziario/);
  assert.doesNotMatch(fleet, /showDeadlinesWorkspace|deadlines-workspace\.js|deadline:open-source/);
  assert.doesNotMatch(vision, /deadlinesWorkspace/);
  assert.match(sections, /Prossime scadenze/);
  for (const label of ["Documenti", "Assicurazioni", "Manutenzioni", "Noleggi"]) {
    assert.match(sections, new RegExp(label));
  }
  assert.match(sections, /data-fve-deadline-source/);
  assert.match(sections, /data-fve-deadline-ids/);
  assert.match(renderer, /upcomingDeadlinesSection/);
  assert.match(navigation, /openFleetDeadlineSource/);
  assert.match(navigation, /deadlineIds/);
  assert.match(navigation, /fleetVisionWorkspace[\s\S]*?workspace\.hidden = true/);
  await assert.rejects(file("assets/js/modules/deadlines-workspace.js"));
  await assert.rejects(file("assets/css/deadlines-workspace.css"));
});

test("Fleet Vision deadline cards open specialist workspaces with source ids", async () => {
  const [aggregator, ...sources] = await Promise.all([
    "assets/js/modules/fleet-vision/aggregator.js",
    "assets/js/modules/documents-workspace.js",
    "assets/js/modules/insurance-workspace.js",
    "assets/js/modules/maintenance-workspace.js",
    "assets/js/modules/rental-workspace.js",
  ].map(file));

  assert.match(aggregator, /decision\.rule === "deadline_soon"/);
  assert.match(aggregator, /decision\.evidence\.source_id/);

  for (const source of sources) {
    assert.match(source, /deadlineIds = null/);
    assert.match(source, /deadlineFilterIds/);
    assert.match(source, /deadlineFilterIds\.has\(Number\(item\.id\)\)/);
  }
});

test("upcoming deadlines cards remain responsive without a fixed canvas", async () => {
  const css = await file("assets/css/fleet-vision-workspace.css");
  assert.match(css, /\.fve2-deadlines>div/);
  assert.match(css, /@media\(max-width:1000px\)[\s\S]*?\.fve2-deadlines>div/);
  assert.match(css, /@media\(max-width:600px\)[\s\S]*?\.fve2-deadlines>div/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

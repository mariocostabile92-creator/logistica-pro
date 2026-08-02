import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("Fleet is prepared while hidden and revealed only after initialization", async () => {
  const navigation = await source("assets/js/modules/view-navigation.js");
  const navigate = navigation.slice(
    navigation.indexOf("async function navigate"),
    navigation.indexOf("function handleNavigationClick"),
  );

  assert.match(navigate, /attachWorkspaceSections\(selectedView\);[\s\S]*await initializeWorkspace\(selectedView\);/);
  assert.match(navigate, /await initializeWorkspace\(selectedView\);[\s\S]*showWorkspace\(selectedView\);[\s\S]*announceWorkspace\(selectedView\);/);
  assert.doesNotMatch(navigate, /showWorkspace\(view\)[\s\S]*await initializeWorkspace/);
});

test("Fleet first paint waits for one guarded registry render", async () => {
  const loader = await source("assets/js/modules/workspace-loader.js");
  const fleet = await source("assets/js/modules/fleet-page.js");

  assert.match(loader, /return async \(\) => \{[\s\S]*module\.initFleetPage\(\);[\s\S]*await module\.prepareFleetFirstPaint\(\);/);
  assert.match(loader, /await initialize\(\);[\s\S]*initialized\.add\(view\);/);
  assert.match(fleet, /if \(loaded\) return Promise\.resolve\(\);/);
  assert.match(fleet, /if \(firstPaintPromise\) return firstPaintPromise;/);
  assert.match(fleet, /firstPaintPromise = refreshFleet\(\)/);
});

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

test("Fleet reveals its definitive skeleton without waiting for registry data", async () => {
  const loader = await source("assets/js/modules/workspace-loader.js");
  const fleet = await source("assets/js/modules/fleet-page.js");

  assert.match(loader, /return \(\) => \{[\s\S]*module\.initFleetPage\(\);[\s\S]*module\.prepareFleetFirstPaint\(\);/);
  assert.doesNotMatch(loader, /await module\.prepareFleetFirstPaint\(\)/);
  assert.match(loader, /await initialize\(\);[\s\S]*initialized\.add\(view\);/);
  assert.match(fleet, /if \(loaded\) return Promise\.resolve\(\);/);
  assert.match(fleet, /if \(firstPaintPromise\) return firstPaintPromise;/);
  assert.match(fleet, /firstPaintPromise = refreshFleet\(\)/);
  assert.match(fleet, /loaded \|\| firstPaintPromise/);
});

test("Fleet secondary workspaces are loaded only when requested", async () => {
  const fleet = await source("assets/js/modules/fleet-page.js");

  for (const module of [
    "damage-workspace", "maintenance-workspace", "documents-workspace",
    "journal-control-room", "fleet-vision-workspace", "vehicle-dossier/loader",
  ]) {
    assert.match(fleet, new RegExp(`import\\("\\./${module}\\.js(?:\\?v=\\d+)?"\\)`));
    assert.doesNotMatch(fleet, new RegExp(`^import .* from "\\./${module}\\.js`, "m"));
  }
});

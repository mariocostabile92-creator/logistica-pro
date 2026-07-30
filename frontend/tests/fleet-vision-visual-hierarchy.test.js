import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Fleet Vision overrides the global white button text on light controls", async () => {
  const css = await file("assets/css/fleet-vision-workspace.css");
  for (const selector of [".fve2-kpi", ".fve2-filters button",
    ".fve2-priority-group>button", ".fve2-vehicle-toggle",
    ".fve2-open-action", ".fve2-quick-action"]) {
    assert.match(css, new RegExp(selector.replace(/[.>]/g, token =>
      token === "." ? "\\." : ">")));
  }
  assert.match(css, /color:#1d2624/);
  assert.match(css, /color:var\(--accent-dark\)/);
  assert.match(css, /:focus-visible/);
});

test("closed vehicle cards expose plate count level and expansion affordance", async () => {
  const sections = await file("assets/js/modules/fleet-vision/sections.js");
  assert.match(sections, /level = priorityLabel/);
  assert.match(sections, /criticità · livello/);
  assert.match(sections, /Espandi/);
  assert.match(sections, /Riduci/);
  assert.match(sections, /aria-expanded/);
});

test("loading state uses visible skeletons and live busy semantics", async () => {
  const [module, css] = await Promise.all([
    file("assets/js/modules/fleet-vision-workspace.js"),
    file("assets/css/fleet-vision-workspace.css"),
  ]);
  assert.match(module, /fve2-loading/);
  assert.match(module, /aria-busy="true"/);
  assert.match(module, /fve2-skeleton/);
  assert.match(css, /\.fve2-skeleton/);
  assert.match(css, /prefers-reduced-motion/);
});

test("mobile controls remain touch friendly and wrap without horizontal scrolling", async () => {
  const css = await file("assets/css/fleet-vision-workspace.css");
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /min-height:44px/);
  assert.match(css, /white-space:normal/);
  assert.doesNotMatch(css, /width:(?:390|768|1440)px/);
});

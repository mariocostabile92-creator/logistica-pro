import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const source = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");


test("Workforce foundation asks the dispatcher how many people are callable", async () => {
  const html = await source("index.html");
  assert.match(html, /Quante persone posso convocare\?/);
  for (const label of [
    "Organico totale", "Convocabili", "Disponibili", "Ferie", "Malattia",
    "Permesso", "Riposo", "Non convocabili", "Override attivi",
  ]) assert.match(html, new RegExp(label));
  assert.doesNotMatch(html, /workforce-foundation[\s\S]{0,3000}(Costo|Marginalita|POD|DNR|DCR)/i);
});


test("Workforce foundation is modular and uses one shared API", async () => {
  const [page, foundation, api] = await Promise.all([
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/modules/workforce-foundation.js"),
    source("assets/js/api.js"),
  ]);
  assert.match(page, /workforce-foundation\.js/);
  assert.match(foundation, /renderWorkforceFoundation/);
  assert.match(api, /api\/plugins\/workforce\/v1\/foundation/);
  assert.doesNotMatch(foundation, /fetch\s*\(/);
});


test("Planning reads callable Workforce drivers without moving assignments into Workforce", async () => {
  const [renderer, routes, foundation] = await Promise.all([
    source("assets/js/modules/planning-operations/renderer.js"),
    source("assets/js/modules/planning-operations/routes.js"),
    source("assets/js/modules/workforce-foundation.js"),
  ]);
  assert.match(renderer, /payload\.workforce/);
  assert.match(renderer, /planningDriverOptions/);
  assert.match(routes, /planningWorkforceDrivers/);
  assert.doesNotMatch(foundation, /assignment|save.*convocation/i);
});


test("Workforce foundation covers desktop tablet and 390 px without fixed canvas", async () => {
  const css = await source("assets/css/workforce-foundation.css");
  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.doesNotMatch(css, /width:\s*(?:768|390|1440)px/);
});

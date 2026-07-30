import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Franchigie is an active inline Fleet workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/franchise-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="franchises"/);
  assert.doesNotMatch(page, /data-fleet-module="franchises"[^>]*disabled|Franchigie\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="franchiseWorkspace"/);
  assert.match(fleet, /showFranchiseWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("workspace provides master detail workflow and contractual origin", async () => {
  const module = await file("assets/js/modules/franchise-workspace.js");
  for (const text of [
    "Gestione delle franchigie contrattuali dei mezzi",
    "Da valutare", "In verifica", "Applicata", "Non applicabile", "Chiusa",
    "Franchigia prevista", "Pratica danno", "Manutenzione",
    "Motivazione", "Torna alla lista",
    "L’importo è letto in tempo reale dal Fleet Asset Profile",
  ]) assert.match(module, new RegExp(text));
  assert.match(module, /franchise-navigator/);
  assert.match(module, /updateFranchiseCase/);
});

test("Damage opens franchise and shows expected deductible", async () => {
  const damage = await file("assets/js/modules/damage-workspace.js");
  assert.match(damage, /Apri Franchigia/);
  assert.match(damage, /ensureFranchiseCase/);
  assert.match(damage, /franchise:open/);
  assert.match(damage, /Franchigia prevista/);
});

test("Maintenance and Vehicle Library expose franchise context", async () => {
  const [maintenance, page, fleet, view] = await Promise.all([
    file("assets/js/modules/maintenance-workspace.js"), file("index.html"),
    file("assets/js/modules/fleet-page.js"), file("assets/js/modules/fleet-view.js"),
  ]);
  assert.match(maintenance, /Franchigia prevista/);
  assert.match(page, /fleetDossierFranchises/);
  assert.match(page, /fleetDossierManageFranchises/);
  assert.match(fleet, /listFranchiseCases/);
  assert.match(view, /franchise_expected/);
});

test("responsive franchise layout supports desktop tablet and 390 px", async () => {
  const css = await file("assets/css/franchise-workspace.css");
  assert.match(css, /grid-template-columns:\s*minmax\(360px,\s*\.95fr\)\s+minmax\(0,\s*1\.25fr\)/);
  assert.match(css, /@media \(max-width:\s*900px\)/);
  assert.match(css, /@media \(max-width:\s*600px\)/);
  assert.match(css, /\.franchise-mobile-back/);
  assert.match(css, /min-width:\s*0/);
  assert.doesNotMatch(css, /width:\s*(?:1440|768|390)px/);
});

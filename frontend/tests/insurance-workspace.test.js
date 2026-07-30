import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Assicurazioni is an active inline Fleet workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/insurance-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="insurance"/);
  assert.doesNotMatch(page, /data-fleet-module="insurance"[^>]*disabled|Assicurazioni\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="insuranceWorkspace"/);
  assert.match(fleet, /showInsuranceWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("insurance workspace supports policy creation editing and master detail", async () => {
  const module = await file("assets/js/modules/insurance-workspace.js");
  for (const text of [
    "Gestione delle coperture assicurative del parco mezzi",
    "Nuova polizza", "Modifica polizza", "Compagnia assicurativa",
    "Numero polizza", "Tipo copertura", "Massimale",
    "Franchigia assicurativa", "Torna alla lista",
    "Attiva", "In scadenza", "Scaduta", "Sospesa",
  ]) assert.match(module, new RegExp(text));
  for (const coverage of [
    "RCA", "Kasko", "Furto e Incendio", "Cristalli",
    "Eventi atmosferici", "Assistenza", "Altro",
  ]) assert.match(module, new RegExp(coverage));
  assert.match(module, /createInsurancePolicy/);
  assert.match(module, /updateInsurancePolicy/);
  assert.match(module, /insurance-navigator/);
});

test("Vehicle Library Damage and Franchigie read the shared policy", async () => {
  const [page, fleet, view, damage, franchise] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/fleet-view.js"), file("assets/js/modules/damage-workspace.js"),
    file("assets/js/modules/franchise-workspace.js"),
  ]);
  assert.match(page, /fleetDossierInsurance/);
  assert.match(page, /Gestisci assicurazione/);
  assert.match(fleet, /listInsurancePolicies/);
  assert.match(view, /policy_number/);
  assert.match(damage, /Polizza associata/);
  assert.match(damage, /Apri Assicurazione/);
  assert.match(franchise, /Compagnia assicurativa/);
  assert.match(franchise, /Numero polizza/);
  assert.match(franchise, /Tipo copertura/);
});

test("insurance responsive layout supports desktop tablet and 390 px", async () => {
  const css = await file("assets/css/insurance-workspace.css");
  assert.match(css, /grid-template-columns:\s*minmax\(360px,\s*\.95fr\)\s+minmax\(0,\s*1\.25fr\)/);
  assert.match(css, /@media \(max-width:\s*900px\)/);
  assert.match(css, /@media \(max-width:\s*600px\)/);
  assert.match(css, /\.insurance-mobile-back/);
  assert.match(css, /min-width:\s*0/);
  assert.doesNotMatch(css, /width:\s*(?:1440|768|390)px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Fleet Vision Engine is an active inline workspace", async () => {
  const [page, fleet, module] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/fleet-vision-workspace.js"),
  ]);
  assert.match(page, /data-fleet-module="vision"/);
  assert.doesNotMatch(page, /Fleet Vision Engine\s*<span class="tag">Prossimamente/);
  assert.match(page, /id="fleetVisionWorkspace"/);
  assert.match(fleet, /showFleetVisionWorkspace/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
});

test("Fleet Vision exposes objective KPIs and correlated module data", async () => {
  const module = await file("assets/js/modules/fleet-vision-workspace.js");
  for (const text of ["Vista unificata e analisi del parco mezzi", "Mezzi operativi",
    "Mezzi indisponibili", "Mezzi in manutenzione", "Danni aperti",
    "Manutenzioni aperte", "Noleggi attivi", "Tipo contratto",
    "Documenti mancanti", "Franchigie aperte", "Scadenze imminenti",
    "Giorni fermo", "Apri Danni", "Apri Manutenzioni", "Apri Documenti",
    "Apri dossier mezzo", "Torna alla lista", "Fleet Health",
    "Cronologia unificata", "Insight correlati", "Apri modulo origine",
    "Assicurazioni scadute", "Contratti in scadenza", "Decision Center",
    "Attenzioni generate da regole operative verificabili", "Origine",
    "Modulo", "Perché", "Apri", "Azioni consigliate", "Azioni critiche",
    "Azioni importanti", "Azioni informative", "Documentazione",
    "Operatività", "Contratti", "Vai al modulo"]) assert.match(module, new RegExp(text));
  assert.match(module, /data-fve-action="\$\{escapeHtml\(decision\.module\)\}"/);
  assert.match(module, /priority-\$\{escapeHtml\(decision\.priority\)\}/);
  assert.match(module, /response\.actions \|\| \[\]/);
  assert.match(module, /data-fve-action-vehicle/);
  assert.doesNotMatch(module, /risk.?score|preditt|machine learning|heatmap/i);
  assert.match(module, /getFleetVision/);
});

test("Vehicle Library opens Fleet Vision filtered by vehicle", async () => {
  const [page, fleet] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
  ]);
  assert.match(page, /fleetDossierOpenVision/);
  assert.match(fleet, /showFleetVisionWorkspace\(\{ vehicle_id: state\.fleetPlugin\.selectedAssetId \}\)/);
});

test("Fleet Vision responsive layout has no fixed canvas", async () => {
  const css = await file("assets/css/fleet-vision-workspace.css");
  assert.match(css, /grid-template-columns:minmax\(280px,.75fr\) minmax\(0,1.6fr\)/);
  assert.match(css, /@media\(max-width:1000px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.fve-back/);
  assert.match(css, /\.fve-timeline/);
  assert.match(css, /\.fve-insights/);
  assert.match(css, /\.fde-decisions/);
  assert.match(css, /\.fde-decision/);
  assert.match(css, /\.fde-action-center/);
  assert.match(css, /\.fde-action-summary/);
  assert.match(css, /\.fde-action-group/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  availabilityPresentation,
  filterFleetAssets,
  fleetDriverLabel,
  fleetRegistryCsv,
  fleetSummary,
} from "../assets/js/modules/fleet-view.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


const assets = [
  {
    id: 1,
    external_identifier: "ASSET-001",
    plate: "AA001AA",
    category: "light_van",
    status: "active",
    availability: "available",
    driver_name: "Risorsa Uno",
    documents: [],
    updated_at: "2026-07-20T08:30:00Z",
  },
  {
    id: 2,
    external_identifier: "ASSET-002",
    plate: "BB002BB",
    category: "large_capacity",
    status: "active",
    availability: "maintenance",
    documents: [{ expires_on: "2026-07-25" }],
    updated_at: "2026-07-21T09:00:00Z",
  },
];


test("Fleet is a registry-first workspace with the requested toolbar and six KPIs", async () => {
  const html = await frontendFile("index.html");
  const fleet = html.slice(
    html.indexOf('id="fleetPluginSection"'),
    html.indexOf('id="settingsSection"'),
  );
  assert.match(fleet, /<h2 id="fleetPluginTitle">Parco Mezzi<\/h2>/);
  for (const id of ["fleetSearchInput", "fleetSyncToggle", "fleetExportBtn"]) {
    assert.match(fleet, new RegExp(`id="${id}"`));
  }
  for (const label of [
    "Totale mezzi", "Disponibili", "In officina", "Indisponibili",
    "Documenti in attenzione", "Nuovi aggiornamenti",
  ]) {
    assert.match(fleet, new RegExp(label));
  }
  assert.match(fleet, /Asset Registry[\s\S]*Registro mezzi/);
  assert.match(fleet, /<th>Targa<\/th>[\s\S]*<th>Stato<\/th>[\s\S]*<th>Driver associato<\/th>[\s\S]*<th>Categoria<\/th>[\s\S]*<th>Ultimo aggiornamento<\/th>/);
  assert.doesNotMatch(fleet, /<th>(Identificativo|Capability|Documenti|Azioni)<\/th>/);
});


test("Fleet status, summary and search remain deterministic without API calls", () => {
  assert.deepEqual(availabilityPresentation("available"), {
    label: "Disponibile",
    tone: "available",
  });
  assert.equal(availabilityPresentation("maintenance").label, "Officina");
  assert.equal(availabilityPresentation("unavailable").label, "Indisponibile");
  assert.equal(availabilityPresentation("reserve").label, "Riserva");
  assert.equal(availabilityPresentation("custom").label, "Da verificare");
  assert.equal(filterFleetAssets(assets, "aa001").length, 1);
  assert.equal(filterFleetAssets(assets, "officina")[0].id, 2);
  assert.equal(filterFleetAssets(assets, "risorsa uno")[0].id, 1);
  assert.deepEqual(fleetSummary(assets, new Date("2026-07-20T00:00:00Z")), {
    total: 2,
    available: 1,
    reserve: 0,
    maintenance: 1,
    unavailable: 0,
    documentsAttention: 1,
  });
});


test("Fleet detail derives an observed driver and export contains only visible registry fields", () => {
  const driver = fleetDriverLabel(assets[1], [{
    event_type: "AssetAssociationChanged",
    occurred_at: "2026-07-21T09:00:00Z",
    details: {
      changes: {
        observed_assigned_human_resource: { before: null, after: "Risorsa Due" },
      },
    },
  }]);
  assert.equal(driver, "Risorsa Due");
  assert.equal(fleetDriverLabel(assets[1]), "Non disponibile");
  const csv = fleetRegistryCsv(assets);
  assert.match(csv, /^"Targa","Stato","Driver associato","Categoria","Ultimo aggiornamento"/);
  assert.match(csv, /"AA001AA","Disponibile","Risorsa Uno"/);
  assert.doesNotMatch(csv, /external_identifier|capabilities|notes|documents/i);
});


test("Fleet detail and Excel update are native dialogs with a responsive registry", async () => {
  const [html, page, sync, fleetCss, syncCss] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/fleet-page.js"),
    frontendFile("assets/js/modules/fleet-sync.js"),
    frontendFile("assets/css/fleet.css"),
    frontendFile("assets/css/fleet-sync.css"),
  ]);
  assert.match(html, /<dialog[\s\S]*?id="fleetSyncPanel"/);
  assert.match(html, /<dialog[\s\S]*?id="fleetAssetDetail"/);
  assert.match(html, /id="fleetAssetPlate"[\s\S]*id="fleetAssetDriver"[\s\S]*id="fleetAssetAvailability"[\s\S]*id="fleetAssetNote"/);
  assert.match(page, /filterFleetAssets\(state\.fleetPlugin\.assets, searchTerm\)/);
  assert.match(page, /response\.items\.length > 0 && document\.body\.dataset\.workspaceState !== "DEMO"/);
  assert.match(page, /latestSync\?\.imported_at \|\| latestFleetImportAt \|\| latestAssetUpdate/);
  assert.match(page, /new Blob/);
  assert.match(page, /now\.getFullYear\(\)[\s\S]*now\.getMonth\(\) \+ 1[\s\S]*now\.getDate\(\)/);
  assert.match(sync, /if \(!panel\.open\) panel\.showModal\(\)/);
  assert.match(sync, /byId\("fleetSyncPanel"\)\.close\(\)/);
  assert.match(fleetCss, /grid-template-columns: repeat\(6, minmax\(0, 1fr\)\)/);
  assert.match(fleetCss, /@media \(max-width: 720px\)[\s\S]*?\.fleet-table-wrap[\s\S]*?display: none/);
  assert.match(fleetCss, /\.fleet-asset-detail[\s\S]*?position: fixed/);
  assert.match(syncCss, /max-height: calc\(100dvh - 32px\)/);
  assert.doesNotMatch(`${page}\n${sync}`, /fetch\(|console\.(log|warn|error)/);
});

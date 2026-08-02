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
import {
  filterOperationalDocuments,
} from "../assets/js/modules/vehicle-library/operational-documents.js";


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
  assert.match(fleet, /Vehicle Library[\s\S]*Schede mezzo/);
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
  assert.equal(availabilityPresentation("disponibile_con_limitazioni").label, "Disponibile con limitazioni");
  assert.equal(availabilityPresentation("in_manutenzione").label, "In manutenzione");
  assert.equal(availabilityPresentation("in_officina").label, "In officina");
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
  assert.equal(fleetDriverLabel(assets[1]), "Non associato");
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


test("Fleet mobile cards prioritize status and plate without removing metadata", async () => {
  const [fleetCss, view] = await Promise.all([
    frontendFile("assets/css/fleet.css"),
    frontendFile("assets/js/modules/fleet-view.js"),
  ]);

  assert.match(
    fleetCss,
    /@media \(max-width: 620px\)[\s\S]*?\.fleet-card-heading \.fleet-status-badge[\s\S]*?order: -1/,
  );
  assert.match(
    fleetCss,
    /@media \(max-width: 620px\)[\s\S]*?\.fleet-card-grid[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  for (const label of ["Driver associato", "Categoria", "Aggiornato"]) {
    assert.match(view, new RegExp(label));
  }
});


test("Fleet P1 retains secondary data while reducing missing-value and timestamp noise", async () => {
  const [html, view, page, css] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/fleet-view.js"),
    frontendFile("assets/js/modules/fleet-page.js"),
    frontendFile("assets/css/fleet.css"),
  ]);

  for (const value of ["Non associato", "Non indicata", "Non registrato"]) {
    assert.match(view, new RegExp(value));
  }
  assert.match(view, /fleet-secondary-value/);
  assert.match(view, /fleet-timestamp/);
  assert.match(html, /data-kpi="unavailable"/);
  assert.match(html, /data-kpi="documents"/);
  assert.match(page, /setFleetMetricPriority\("fleetRecentUpdates"/);
  assert.match(css, /\.fleet-secondary-value[\s\S]*?color: var\(--text-muted\)/);
  assert.match(css, /\.fleet-summary > div\[data-priority="attention"\]/);
  assert.match(css, /\.fleet-summary > div\[data-priority="critical"\]/);
});


test("Fleet tree navigation follows the Fleet Manager workflow", async () => {
  const [html, css, page, view, journal, vehicle] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/css/fleet.css"),
    frontendFile("assets/js/modules/fleet-page.js"),
    frontendFile("assets/js/modules/fleet-view.js"),
    frontendFile("journal/index.html"),
    frontendFile("vehicles/index.html"),
  ]);
  const primary = html.match(
    /<nav class="workspace-tabs"[\s\S]*?<\/nav>/,
  )?.[0] || "";
  const fleet = html.match(
    /<nav class="fleet-tree"[\s\S]*?<\/nav>/,
  )?.[0] || "";
  assert.doesNotMatch(primary, /Giornale di bordo|\/app\/journal\//);
  for (const item of ["Parco Mezzi", "Vehicle Library", "Giornale di bordo"]) {
    assert.match(fleet, new RegExp(item));
  }
  for (const module of ["documents", "franchises", "rentals", "vision"]) {
    const node = fleet.match(new RegExp(`data-fleet-module="${module}"[\\s\\S]*?<\\/button>`))?.[0] || "";
    assert.doesNotMatch(node, /Prossimamente|disabled/);
  }
  assert.match(fleet, /data-fleet-module="damage"[\s\S]*?Danni/);
  assert.doesNotMatch(
    fleet.match(/data-fleet-module="damage"[\s\S]*?<\/button>/)?.[0] || "",
    /Prossimamente|disabled/,
  );
  assert.match(page, /showJournalControlRoom/);
  assert.match(journal, /Driver|Journal|Giornale/i);
  assert.match(html, /id="fleetAssetTree"[\s\S]*?id="fleetTreeAssets"/);
  assert.match(html, /id="fleetVehicleDossier"/);
  assert.match(css, /\.fleet-workspace-layout/);
  assert.match(css, /grid-template-columns: 248px minmax\(0, 1fr\)/);
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*?transform: translateX\(-105%\)/);
  assert.match(page, /loadVehicleDossier\(assetId\)/);
  assert.match(page, /byId\("fleetAssetTree"\)\.open = false/);
  assert.doesNotMatch(
    page,
    /history\.pushState|location\.href\s*=|window\.open\(/,
  );
  assert.match(view, /renderFleetTree/);
  assert.match(view, /renderVehicleDossier/);
  for (const page of [journal, vehicle]) {
    const nav = page.match(
      /<nav class="workspace-tabs"[\s\S]*?<\/nav>/,
    )?.[0] || "";
    assert.doesNotMatch(nav, /Giornale di bordo|\/app\/journal\//);
  }
});


test("Vehicle Library is a read-only operational record using the shared shell", async () => {
  const [html, script, css, fleetHtml, fleetView, documents] = await Promise.all([
    frontendFile("vehicles/index.html"),
    frontendFile("assets/js/modules/vehicle-library/index.js"),
    frontendFile("assets/css/vehicle-library.css"),
    frontendFile("index.html"),
    frontendFile("assets/js/modules/fleet-view.js"),
    frontendFile("assets/js/modules/vehicle-library/operational-documents.js"),
  ]);

  assert.match(html, /Operations Engine/);
  assert.match(html, /Vehicle Library · Cartella operativa/);
  assert.match(html, /aria-current="page">Fleet/);
  assert.match(html, /Documenti operativi/);
  for (const value of [
    "Km attuali",
    "Ultimo utilizzo",
    "Giorni fermo",
    "Ultimo driver dichiarato",
    "Ultima movimentazione",
  ]) {
    assert.match(html, new RegExp(value));
  }
  assert.match(script, /getFleetVehicleHistory\(assetId\)/);
  assert.match(documents, /Video non disponibili in questa versione/);
  for (const filter of ["check_out", "check_in", "anomaly", "no_anomaly", "last_7_days", "last_30_days"]) {
    assert.match(html, new RegExp(`data-document-filter="${filter}"`));
    assert.match(fleetHtml, new RegExp(`data-document-filter="${filter}"`));
  }
  assert.match(documents, /Identificativo documento/);
  assert.match(documents, /Registrazione completata/);
  assert.match(documents, /Fleet Vision Engine/);
  assert.doesNotMatch(script, /method:\s*["'](?:POST|PATCH|PUT|DELETE)/);
  assert.doesNotMatch(documents, /method:\s*["'](?:POST|PATCH|PUT|DELETE)/);
  assert.match(css, /@media \(max-width: 480px\)/);
  assert.match(css, /\.movement-timeline/);
  assert.match(fleetHtml, /id="openVehicleLibrary"/);
  assert.match(fleetView, /\/app\/vehicles\/\?id=/);
});

test("operational documents support movement, anomaly, period and text filters", () => {
  const movements = [
    {
      id: "11111111-aaaa",
      operation_type: "check_out",
      occurred_at: "2026-07-29T08:00:00Z",
      declared_driver_identifier: "Mario Rossi",
      plate_snapshot: "AB123CD",
      anomaly_present: false,
    },
    {
      id: "22222222-bbbb",
      operation_type: "check_in",
      occurred_at: "2026-06-01T18:00:00Z",
      declared_driver_identifier: "Luigi Bianchi",
      plate_snapshot: "AB123CD",
      anomaly_present: true,
    },
  ];
  const now = new Date("2026-07-30T12:00:00Z");
  assert.deepEqual(filterOperationalDocuments(movements, { filter: "check_out", now }).map(({ id }) => id), ["11111111-aaaa"]);
  assert.deepEqual(filterOperationalDocuments(movements, { filter: "anomaly", now }).map(({ id }) => id), ["22222222-bbbb"]);
  assert.deepEqual(filterOperationalDocuments(movements, { filter: "last_7_days", now }).map(({ id }) => id), ["11111111-aaaa"]);
  assert.deepEqual(filterOperationalDocuments(movements, { query: "rientro", now }).map(({ id }) => id), ["22222222-bbbb"]);
  assert.deepEqual(filterOperationalDocuments(movements, { query: "Mario Rossi", now }).map(({ id }) => id), ["11111111-aaaa"]);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { fleetSummary } from "../assets/js/modules/fleet-view.js";
import {
  assetValueLabel,
  operationalCodeLabel,
} from "../assets/js/utils/formatters.js";


const frontendFile = (path) => readFile(
  new URL(`../${path}`, import.meta.url),
  "utf8",
);


test("primary navigation is administrative and routes Journal through Fleet", async () => {
  const [html, layout] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/css/layout.css"),
  ]);
  const navigation = html.match(
    /<nav class="workspace-tabs"[\s\S]*?<\/nav>/,
  )?.[0] || "";

  assert.match(navigation, /data-workspace-view="home"/);
  assert.match(navigation, /data-workspace-view="operations"/);
  assert.match(
    navigation,
    /data-workspace-view="operations"[\s\S]*?>\s*Planning\s*<\/button>/,
  );
  assert.match(navigation, /data-workspace-view="workforce"/);
  assert.match(navigation, /data-workspace-view="fleet"/);
  assert.match(navigation, /data-workspace-view="learn"/);
  assert.doesNotMatch(navigation, /Giornale di bordo|\/app\/journal\//);
  const fleet = html.match(
    /<nav class="fleet-tree"[\s\S]*?<\/nav>/,
  )?.[0] || "";
  assert.match(fleet, /data-fleet-module="journal"[\s\S]*?Giornale di bordo/);
  assert.match(fleet, /Vehicle Library/);
  assert.doesNotMatch(navigation, /settings|getting-started/i);
  assert.match(html, /id="configurationNavBtn"/);
  assert.match(layout, /\.workspace-tab\.active,[\s\S]*\.workspace-tab\.active:hover:not\(:disabled\)/);
});


test("visible branding uses Operations Engine", async () => {
  const html = await frontendFile("index.html");

  assert.match(html, /<title>Operations Engine<\/title>/);
  assert.match(html, /class="product-brand oe-header-brand"[\s\S]*operations-engine-logo\.png\?v=1[\s\S]*alt="Operations Engine"/);
  assert.doesNotMatch(html, /<h1>Operations Engine<\/h1>/);
  assert.doesNotMatch(html, /<h1>DSP Operations OS<\/h1>/);
});


test("Journal uses Operations Engine tokens in a standalone driver shell", async () => {
  const [journal, layout, components, responsive] = await Promise.all([
    frontendFile("journal/index.html"),
    frontendFile("assets/css/driver-journal-layout.css"),
    frontendFile("assets/css/driver-journal-components.css"),
    frontendFile("assets/css/driver-journal-responsive.css"),
  ]);

  assert.match(journal, /<h1[^>]*>Giornale di bordo<\/h1>/);
  assert.match(journal, /id="startButton"[^>]*>Inizia/);
  assert.doesNotMatch(journal, /class="workspace-tabs"/);
  assert.doesNotMatch(journal, /Planning|Workforce|Configurazione/);
  assert.match(journal, /id="healthStatus"/);
  assert.match(journal, /assets\/css\/base\.css/);
  assert.match(journal, /assets\/css\/components\.css/);
  assert.match(layout, /\.journal-workspace/);
  assert.match(components, /var\(--surface\)/);
  assert.match(responsive, /@media \(max-width: 768px\)/);
  assert.match(responsive, /\.journal-mobile-context/);
  assert.doesNotMatch(journal, /MyJob/i);
});


test("Home and Operations use progressive disclosure", async () => {
  const [html, navigation, layout] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/view-navigation.js"),
    frontendFile("assets/css/layout.css"),
  ]);

  assert.match(navigation, /home: HOME_SECTIONS/);
  assert.match(navigation, /operations: OPERATIONS_SECTIONS/);
  assert.match(html, /id="missionControlSection"/);
  assert.doesNotMatch(html, /id="briefingSection"/);
  assert.match(layout, /data-planning-state="empty"[\s\S]*#dashboardSection/);
  assert.match(html, /id="importsDisclosure"[\s\S]*Gestisci dati di origine/);
});


test("Operations presents assignments before conflicts and Capacity", async () => {
  const html = await frontendFile("index.html");
  const assignments = html.indexOf('id="assignmentTableBody"');
  const conflicts = html.indexOf('id="planningIssuesTitle"');
  const capacity = html.indexOf('id="stationCapacityTitle"');

  assert.ok(assignments > 0);
  assert.ok(assignments < conflicts);
  assert.ok(conflicts < capacity);
  assert.match(html, /disponibili dopo la generazione del Planning\./i);
});


test("Fleet summary is deterministic and empty state supports demo", async () => {
  const source = await frontendFile("assets/js/modules/fleet-view.js");
  const summary = fleetSummary([
    {
      availability: "available",
      documents: [{ expires_on: "2026-08-01" }],
    },
    {
      availability: "reserve",
      documents: [{ expires_on: "2026-09-30" }],
    },
    {
      availability: "maintenance",
      documents: [{ expires_on: "2026-07-01" }],
    },
  ], new Date("2026-07-20T00:00:00Z"));

  assert.deepEqual(summary, {
    total: 3,
    available: 1,
    reserve: 1,
    maintenance: 1,
    unavailable: 0,
    documentsAttention: 2,
  });
  assert.match(source, /Nessun mezzo registrato/);
  assert.match(source, /Importa Stato Parco/);
  assert.match(source, /secondaryActionLabel: demoEnabled/);
  assert.match(source, /visual: "fleet"/);
  assert.equal(assetValueLabel("light_van"), "Furgone leggero");
  assert.equal(assetValueLabel("large_capacity"), "Grande capacità");
  assert.equal(
    operationalCodeLabel("DRIVER_ABSENT_REPLACED"),
    "Risorsa assente sostituita",
  );
});


test("Configuration values are hidden behind accessible disclosures", async () => {
  const [html, source] = await Promise.all([
    frontendFile("index.html"),
    frontendFile("assets/js/modules/settings-view.js"),
  ]);

  assert.match(html, /<h2 id="settingsTitle">Configurazione<\/h2>/);
  assert.match(html, /<details class="settings-scope-disclosure">/);
  assert.match(source, /<details class="settings-config-section">/);
  assert.match(source, /<summary>/);
  assert.match(source, /elementi/);
  assert.match(source, /Default piattaforma/);
});


test("Learn provides compact internal navigation for core topics", async () => {
  const html = await frontendFile("index.html");

  assert.match(html, /<h2 id="learnTitle">Learn<\/h2>/);
  assert.match(html, /class="learn-index"/);
  for (const topic of [
    "Import dei dati",
    "Planning",
    "Fleet",
    "Briefing operativo",
    "FAQ iniziale",
  ]) {
    assert.match(html, new RegExp(topic));
  }
});


test("design system covers wide desktop tablet and mobile breakpoints", async () => {
  const [layout, responsive, onboarding, briefing] = await Promise.all([
    frontendFile("assets/css/layout.css"),
    frontendFile("assets/css/responsive.css"),
    frontendFile("assets/css/onboarding.css"),
    frontendFile("assets/css/briefing.css"),
  ]);
  const css = `${layout}\n${responsive}\n${onboarding}\n${briefing}`;

  assert.match(layout, /min\(1360px,/);
  assert.match(css, /@media \(max-width: 1180px\)/);
  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(responsive, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(
    briefing,
    /@media \(max-width: 980px\)[\s\S]*?\.briefing-metrics[\s\S]*?repeat\(2,/,
  );
});


test("UX modules keep sanitized logging and no new business API", async () => {
  const paths = [
    "assets/js/modules/onboarding.js",
    "assets/js/modules/briefing.js",
    "assets/js/modules/fleet-page.js",
    "assets/js/modules/settings-view.js",
    "assets/js/modules/view-navigation.js",
  ];
  const sources = await Promise.all(paths.map(frontendFile));
  const combined = sources.join("\n");

  assert.doesNotMatch(combined, /console\.(error|warn|log)/);
  assert.doesNotMatch(combined, /fetch\(/);
  assert.match(combined, /aria-expanded|workspace:navigate/);
});

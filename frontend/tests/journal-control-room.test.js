import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Giornale di bordo opens the inline Journal Control Room", async () => {
  const [page, fleet, module, publicJournal] = await Promise.all([
    file("index.html"), file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/journal-control-room.js"),
    file("journal/index.html"),
  ]);
  assert.match(page, /data-fleet-module="journal"/);
  assert.match(page, /id="journalControlRoom"/);
  assert.match(fleet, /showJournalControlRoom/);
  assert.doesNotMatch(module, /location\.reload|location\.href|history\.pushState/);
  assert.match(publicJournal, /Driver|Journal|Giornale/i);
});

test("Control Room is a live driver overview with a concise monitoring detail", async () => {
  const [module, components, renderer, shared, overview, liveDetail, presenter] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-control-room/components.js"),
    file("assets/js/modules/journal-control-room/renderer.js"),
    file("assets/js/modules/journal-shared-access.js"),
    file("assets/js/modules/journal-control-room/live-overview.js"),
    file("assets/js/modules/journal-control-room/live-detail.js"),
    file("assets/js/modules/journal-control-room/live-status-presenter.js"),
  ]);
  const presentation = components + renderer + shared + overview + liveDetail + presenter;
  for (const text of ["Journal Control Room", "Driver attesi", "Non iniziati",
    "In compilazione", "Completati", "Con anomalie", "In ritardo", "giornata corrente",
    "Archivio GDB", "Apri monitoraggio", "Monitoraggio live", "Timeline essenziale",
    "Apri GDB completo", "Torna alla lista", "Generata", "Aperta", "Completata",
    "link condiviso", "Origine"]) {
    assert.match(presentation + module, new RegExp(text, "i"));
  }
  assert.match(module, /listJournalControlRoom/);
  assert.match(module, /data-jcr-search/);
  assert.match(module, /data-jcr-detail/);
  assert.match(module, /if \(target\) target\.textContent/);
  assert.match(module, /params\.live_status = state\.live_filter/);
  assert.match(overview, /data-jcr-live-filter/);
  assert.doesNotMatch(presentation + module, /Ultimi 7 giorni|Ultimi 30 giorni|data-jcr-period/);
  assert.doesNotMatch(module, /Genera procedura Driver|createJournalDriverSession|journalSessionGenerator/);
  assert.doesNotMatch(liveDetail, /Dotazioni e checklist|Carburante|Pulizia|Avvisi Smart/);
});

test("canonical driver identifiers remain internal in cards and live monitoring", async () => {
  const [{ journalLiveCard }, { journalLiveDetail }, { driverDisplayName }] = await Promise.all([
    import(new URL("../assets/js/modules/journal-control-room/live-overview.js", import.meta.url)),
    import(new URL("../assets/js/modules/journal-control-room/live-detail.js", import.meta.url)),
    import(new URL("../assets/js/modules/journal-control-room/driver-display.js", import.meta.url)),
  ]);
  const item = {
    id: "session-1",
    declared_driver_identifier: "source-3acf08730cb8c7a0",
    driver_name: "Alessandro",
    driver_surname: "Facchetti",
    plate_snapshot: "GC298NZ",
    vehicle_model: "Iveco Daily",
    status: "opened",
    operation_type: "check_out",
    origin: "Shared link",
    created_at: "2026-08-08T08:00:00+00:00",
    opened_at: "2026-08-08T08:05:00+00:00",
    occurred_at: "2026-08-08T08:05:00+00:00",
    operational_date: "2026-08-08",
    media: [],
    anomaly_present: false,
    incomplete: true,
    is_late: false,
  };
  const presentation = journalLiveCard(item, item.id) + journalLiveDetail(item);
  assert.match(presentation, /Alessandro Facchetti/);
  assert.doesNotMatch(presentation, /source-3acf08730cb8c7a0/);
  assert.equal(driverDisplayName({
    declared_driver_identifier: "Mario Rossi",
  }), "Mario Rossi");
  assert.equal(driverDisplayName({
    driver_display_name: "Giulia Bianchi",
    declared_driver_identifier: "source-workforce-id",
  }), "Giulia Bianchi");
  assert.equal(driverDisplayName({
    declared_driver_identifier: "source-not-for-display",
  }), "Driver non disponibile");
});

test("Control Room and complete Archive detail link Vehicle Library and Damage", async () => {
  const [renderer, fleet, module, archiveDetail] = await Promise.all([
    file("assets/js/modules/vehicle-dossier/renderer.js"),
    file("assets/js/modules/fleet-page.js"),
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-control-room/archive-detail.js"),
  ]);
  assert.match(renderer, /Vai al Journal/);
  assert.match(fleet, /showJournalControlRoom\(\{ vehicle_id: vehicleId\(\) \}\)/);
  assert.match(module, /fleet:vehicle-open/);
  assert.match(module, /damage:open/);
  assert.match(archiveDetail, /damage_case_number/);
  assert.match(archiveDetail, /Anomalia da gestire/);
  for (const section of ["Identificazione", "Dati operativi", "Dotazioni e checklist",
    "Anomalie", "Timeline completa", "Azioni"]) assert.match(archiveDetail, new RegExp(section));
});

test("Control Room responsive CSS supports desktop tablet and mobile", async () => {
  const css = await file("assets/css/journal-control-room.css");
  assert.match(css, /grid-template-columns:minmax\(320px,.85fr\) minmax\(0,1.4fr\)/);
  assert.match(css, /@media\(max-width:900px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /\.jcr-back/);
  assert.match(css, /\.jcr-warnings/);
  assert.match(css, /box-sizing:border-box/);
  assert.doesNotMatch(css, /width:(?:1440|768|390)px/);
});

test("shared link is primary and DJ-003 query sessions remain compatible", async () => {
  const [page, index, access, flow, api] = await Promise.all([
    file("journal/index.html"),
    file("assets/js/modules/driver-journal/index.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
    file("assets/js/modules/driver-journal/flow.js"),
    file("assets/js/modules/driver-journal/api.js"),
  ]);
  assert.match(page, /id="sessionContext"/);
  assert.match(page, /id="startButton"[^>]*>Inizia/);
  assert.match(page, /id="driverName"/);
  assert.match(page, /id="driverSurname"/);
  assert.doesNotMatch(page, /workspace-tabs|Configurazione|Planning/);
  assert.match(access, /URLSearchParams\(location\.search\)\.get\("session"\)/);
  assert.match(access, /getSharedSession/);
  assert.match(access, /createSharedSession/);
  assert.match(access, /readOnly = true/);
  assert.match(access, /state\.step = 4/);
  assert.match(flow, /markSessionInProgress/);
  assert.match(flow, /checkSessionWarnings/);
  assert.match(flow, /createSpontaneousSession/);
  assert.match(api, /sessions\/\$\{encodeURIComponent\(sessionId\)\}/);
  assert.match(api, /sessions\/shared/);
  assert.match(api, /\/warnings/);
  assert.doesNotMatch(index, /localStorage|sessionStorage/);
  assert.match(index, /history\.replaceState\(\{\}, "", "\/app\/journal\/"\)/);
});

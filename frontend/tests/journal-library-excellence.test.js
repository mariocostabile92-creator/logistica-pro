import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Journal workspace exposes inline Control Room and Archivio GDB navigation", async () => {
  const [orchestrator, archive, navigation] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-archive/index.js"),
    file("assets/js/modules/journal-control-room/navigation.js"),
  ]);
  assert.match(orchestrator, /Control Room/);
  assert.match(orchestrator, /Archivio GDB/);
  assert.match(orchestrator, /mountJournalArchive/);
  assert.match(orchestrator, /selectedDate/);
  assert.match(orchestrator, /selectedId/);
  assert.match(archive, /options\.selectedDate/);
  assert.doesNotMatch(orchestrator + archive + navigation, /location\.href|location\.reload|history\.pushState/);
});

test("complete Archive detail owns media metadata fallback and full sections", async () => {
  const [detail, media, components] = await Promise.all([
    file("assets/js/modules/journal-control-room/archive-detail.js"),
    file("assets/js/modules/journal-control-room/media-section.js"),
    file("assets/js/modules/journal-control-room/components.js"),
  ]);
  for (const text of ["Identificazione", "Dati operativi", "Dotazioni e checklist",
    "Anomalie", "Avvisi smart", "Allegati", "Timeline completa", "Azioni",
    "original_filename", "uploaded_at", "Download", "File non disponibile"]) {
    assert.match(detail + media + components, new RegExp(text, "i"));
  }
  assert.match(media, /<video/);
  assert.match(media, /<img/);
  assert.match(media, /addEventListener\("error"/);
});

test("Archive calendar and day filters use dedicated API aggregation", async () => {
  const [calendar, renderer, api, archive, daySummary, timeline, switcher] = await Promise.all([
    file("assets/js/modules/journal-archive/calendar.js"),
    file("assets/js/modules/journal-archive/renderer.js"),
    file("assets/js/api.js"),
    file("assets/js/modules/journal-archive/index.js"),
    file("assets/js/modules/journal-archive/calendar-day-summary.js"),
    file("assets/js/modules/journal-archive/daily-timeline.js"),
    file("assets/js/modules/journal-archive/view-mode-switcher.js"),
  ]);
  for (const text of ["Mese precedente", "Mese successivo", "Oggi", "Totali",
    "Prese in carico", "Rientri", "Complete", "Incomplete", "Con anomalie", "Con media",
    "Targa, driver, note, ID", "Filtra targa", "Filtra driver", "Reimposta"]) assert.match(renderer + calendar, new RegExp(text));
  assert.match(api, /journal-archive\/month/);
  assert.match(api, /journal-archive\/day/);
  assert.match(calendar, /role="grid"/);
  for (const text of ["GDB", "anomalie", "incomplete", "media", "Elenco", "Timeline", "Apri GDB"]) {
    assert.match(daySummary + timeline + switcher, new RegExp(text, "i"));
  }
  assert.match(archive, /state\.currentOperationalDate\?\.startsWith/);
  assert.doesNotMatch(await file("assets/js/modules/journal-archive/state.js"), /new Date\(\)\.toISOString|date\.today/);
});

test("Journal media supports image video multiple retry and submit protection", async () => {
  const [page, media] = await Promise.all([
    file("journal/index.html"),
    file("assets/js/modules/driver-journal/media.js"),
  ]);
  assert.match(page, /video\/mp4/);
  assert.match(page, /video\/quicktime/);
  assert.match(page, /multiple/);
  assert.match(media, /Riprova/);
  assert.match(media, /uploading/);
  assert.match(media, /createElement\("video"\)/);
});

test("essential lower controls have explicit normal hover focus and disabled styles", async () => {
  const css = await file("assets/css/journal-control-room.css");
  assert.match(css, /\.jcr-actions a,.jcr-actions button/);
  assert.match(css, /color:#0d584f!important/);
  assert.match(css, /\.jcr-actions a:hover/);
  assert.match(css, /\.jcr-actions a:focus-visible/);
  assert.match(css, /\.jcr-actions button:disabled/);
  assert.match(css, /opacity:1/);
});

test("archive responsive contract covers tablet and 390px-compatible mobile", async () => {
  const css = await file("assets/css/journal-archive.css");
  assert.match(css, /@media\(max-width:1000px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
  assert.match(css, /minmax\(0,1fr\)/);
  assert.match(css, /overflow-y:scroll/);
  assert.match(css, /max-height:none/);
  assert.doesNotMatch(css, /width:(?:390|768|1440)px/);
});

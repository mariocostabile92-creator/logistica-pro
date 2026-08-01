import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("Journal workspace exposes inline Control Room and Archivio GDB navigation", async () => {
  const [orchestrator, archive] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-archive/index.js"),
  ]);
  assert.match(orchestrator, /Control Room/);
  assert.match(orchestrator, /Archivio GDB/);
  assert.match(orchestrator, /mountJournalArchive/);
  assert.doesNotMatch(orchestrator + archive, /location\.href|location\.reload|history\.pushState/);
});

test("Archive calendar and day filters use dedicated API aggregation", async () => {
  const [calendar, renderer, api] = await Promise.all([
    file("assets/js/modules/journal-archive/calendar.js"),
    file("assets/js/modules/journal-archive/renderer.js"),
    file("assets/js/api.js"),
  ]);
  for (const text of ["Mese precedente", "Mese successivo", "Oggi", "Totali",
    "Prese in carico", "Rientri", "Complete", "Incomplete", "Con anomalie", "Con media",
    "Targa, driver, note, ID", "Reimposta"]) assert.match(renderer + calendar, new RegExp(text));
  assert.match(api, /journal-archive\/month/);
  assert.match(api, /journal-archive\/day/);
  assert.match(calendar, /role="grid"/);
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
  assert.doesNotMatch(css, /width:(?:390|768|1440)px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("Control Room exposes one shared GDB access component", async () => {
  const [room, shared, api, loader] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/journal-shared-access.js"),
    file("assets/js/api.js"),
    file("assets/js/modules/workspace-loader.js"),
  ]);
  assert.match(room, /mountJournalSharedAccess/);
  assert.match(room, /data-jcr-shared-access/);
  for (const label of [
    "Genera link condiviso GDB",
    "Copia link",
    "Apri come Driver",
    "Rigenera",
    "Revoca",
    "Attivo",
  ]) assert.match(shared, new RegExp(label));
  assert.match(shared, /window\.confirm/);
  assert.match(shared, /navigator\.clipboard\.writeText/);
  assert.match(api, /journal-control-room\/shared-access\/active/);
  assert.match(api, /journal-control-room\/shared-access/);
  assert.match(loader, /journal-shared-access\.css/);
  assert.doesNotMatch(shared, /<label>Driver|<label>Targa|procedure_type|scheduled_date/i);
});


test("public journal access validates token and keeps DJ-003 compatibility", async () => {
  const [publicAccess, access, api, state, html] = await Promise.all([
    file("assets/js/modules/driver-journal/public-access.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
    file("assets/js/modules/driver-journal/api.js"),
    file("assets/js/modules/driver-journal/state.js"),
    file("journal/index.html"),
  ]);
  assert.match(publicAccess, /PUBLIC_ACCESS_PATTERN/);
  assert.match(publicAccess, /app\\\/journal\\\/access/);
  assert.match(publicAccess, /validateSharedAccess/);
  assert.match(publicAccess, /showPublicAccessError/);
  assert.match(publicAccess, /journalForm"\)\.hidden = true/);
  assert.match(access, /preparePublicAccess/);
  assert.match(access, /access_token: state\.accessToken/);
  assert.match(access, /URLSearchParams\(location\.search\)\.get\("session"\)/);
  assert.match(api, /shared-access\/\$\{encodeURIComponent\(token\)\}/);
  assert.match(state, /accessToken: null/);
  assert.match(html, /<base href="\/app\/journal\/"/);
  assert.doesNotMatch(html, /Planning|Workforce|Fleet|Control Room/);
});


test("shared access UI is responsive at requested breakpoints", async () => {
  const css = await file("assets/css/journal-shared-access.css");
  assert.match(css, /@media\(max-width:768px\)/);
  assert.match(css, /@media\(max-width:480px\)/);
  assert.match(css, /min-width:0/);
  assert.doesNotMatch(css, /(?<!max-)width:(?:390|768|1440)px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildDriverShiftGroupMessage,
  copyGroupMessage,
  formatGroupMessageDate,
} from "../assets/js/modules/driver-shift-group-message.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const SHARED_URL = "https://operations.example/app/driver-shifts/access/#token=shared-token";
const fixture = () => buildDriverShiftGroupMessage({
  periodStart: "2026-08-17",
  periodEnd: "2026-08-23",
  sharedPortalUrl: SHARED_URL,
});


test("admin exposes the one-message WhatsApp copy CTA", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftGroupMessageCopy"[^>]*>Copia messaggio per il gruppo WhatsApp/);
  assert.doesNotMatch(html, />Invia ai driver</);
});


test("message template contains the complete Italian period", () => {
  assert.equal(formatGroupMessageDate("2026-08-17"), "17 agosto 2026");
  assert.match(fixture(), /turni dal 17 agosto 2026 al 23 agosto 2026/);
});


test("message contains the current shared portal URL", () => {
  assert.match(fixture(), new RegExp(SHARED_URL.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});


test("two hundred recipients still produce exactly one URL", () => {
  const message = fixture();
  assert.equal(message.match(/https?:\/\/\S+/g)?.length, 1);
  assert.equal((message.match(/shared-token/g) || []).length, 1);
});


test("message contains no personal portal URL", () => {
  const message = fixture();
  assert.doesNotMatch(message, /\/app\/driver-shifts\/#token=/);
  assert.doesNotMatch(message, /recipient|workforce_member|personal-token/i);
});


test("message never includes actual access codes PINs names or T-IDs", () => {
  const message = fixture();
  for (const secret of ["Mario Rossi", "AB7K4P2Q", "123456", "T-00991"])
    assert.doesNotMatch(message, new RegExp(secret));
});


test("message includes the acknowledgement instruction", () => {
  assert.match(fixture(), /premere “Ho visto i turni”/);
  assert.match(fixture(), /^Ciao a tutti 👋/);
});


test("clipboard success writes the entire message once", async () => {
  const writes = [];
  assert.equal(await copyGroupMessage(fixture(), {
    writeText: async (value) => writes.push(value),
  }), true);
  assert.deepEqual(writes, [fixture()]);
});


test("clipboard failure is reported without throwing", async () => {
  const copied = await copyGroupMessage(fixture(), {
    writeText: async () => { throw new Error("blocked"); },
  });
  assert.equal(copied, false);
});


test("clipboard failure exposes a selectable readonly fallback", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /id="driverShiftMessageFallbackText" readonly/);
  assert.match(controller, /showMessageFallback\(message\)/);
  assert.match(controller, /messageFallbackText\.select\(\)/);
});


test("missing portal is prepared automatically before copy", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /async function ensureActivePortal/);
  assert.match(controller, /state\.portal = await prepareSharedPortal\(state\.model\.distribution\.id\)/);
  assert.match(controller, /if \(!await ensureActivePortal\(\)\) return/);
});


test("an existing active portal is reused without regeneration", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /if \(state\.portal\?\.status === "ACTIVE" && state\.portal\.access_url\) return true/);
  const ensureBlock = controller.slice(
    controller.indexOf("async function ensureActivePortal"),
    controller.indexOf("async function copyGroupMessageForWhatsApp"),
  );
  assert.doesNotMatch(ensureBlock, /regenerateSharedPortal/);
});


test("partial credential readiness shows the exact warning", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /Accessi pronti: \$\{ready\}\/\$\{total\}/);
  assert.match(controller, /driver non hanno ancora un accesso personale/);
  assert.match(controller, /prepareMissingAccesses/);
});


test("zero ready credentials block group copy", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /elements\.groupCopy\.disabled = !credentialSummary \|\| ready === 0/);
  assert.match(controller, /Prepara almeno un accesso personale prima di copiare il messaggio/);
});


test("198 of 200 ready never requires recipient selection", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  const groupFlow = controller.slice(
    controller.indexOf("async function copyGroupMessageForWhatsApp"),
    controller.indexOf("async function loadPortal"),
  );
  assert.doesNotMatch(groupFlow, /state\.selected|recipientIds|prepareDistributionBatch/);
});


test("copy-only-link remains a secondary fallback", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /id="driverShiftPortalCopy"[^>]*class="secondary">Copia solo link/);
  assert.match(controller, /copyText\(state\.portal\.access_url\)/);
});


test("new planning revision asks for a new message", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /Nuovi turni pubblicati\. Condividi il nuovo messaggio\./);
  assert.match(controller, /state\.planning\.id !== planning\.id/);
  assert.match(controller, /elements\.revisionNotice\.hidden = !state\.newRevision/);
});


test("compact group summary preserves all delivery tracking counters", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  for (const field of ["recipients_total", "opened", "acknowledged", "not_opened"])
    assert.match(controller, new RegExp(`summary\\?\\.${field}`));
  assert.match(controller, /Accessi pronti/);
});


test("group message UI remains usable at 390px", async () => {
  const css = await source("assets/css/driver-shift-distribution.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /#driverShiftGroupMessageCopy\s*{[^}]*min-height:\s*48px/s);
  assert.match(css, /\.driver-shift-group-summary\s*{\s*grid-template-columns:\s*1fr/);
  assert.match(css, /\.driver-shift-message-fallback textarea\s*{\s*max-width:\s*100%/);
  assert.doesNotMatch(css, /width:\s*390px/);
});


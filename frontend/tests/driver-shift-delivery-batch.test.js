import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  filterDistributionRecipients,
  renderDistributionRecipients,
  renderDistributionSummary,
} from "../assets/js/modules/driver-shift-distribution-presenter.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "" });
const recipients = [
  { id: 1, display_name: "Driver Ready", shift_days_count: 5, readiness: "READY", available_channels: ["PHONE"], access_status: "NOT_OPENED", access_revoked: false },
  { id: 2, display_name: "Driver Missing", shift_days_count: 4, readiness: "MISSING_CONTACT", available_channels: [], access_status: "NOT_OPENED", access_revoked: false },
  { id: 3, display_name: "Driver Invalid", shift_days_count: 3, readiness: "INVALID_CONTACT", available_channels: [], access_status: "OPENED", access_revoked: false },
  { id: 4, display_name: "Driver Ack", shift_days_count: 2, readiness: "READY", available_channels: ["EMAIL"], access_status: "ACKNOWLEDGED", access_revoked: false },
];


test("readiness summary exposes contact counters and selected count", () => {
  const target = element();
  renderDistributionSummary(target, {
    recipients_total: 143, contact_ready: 137, missing_contact: 5, invalid_contact: 1,
    opened: 4, acknowledged: 2, not_opened: 139,
  }, 137);
  for (const label of ["Destinatari", "Pronti", "Senza contatto", "Non validi", "Selezionati"]) {
    assert.match(target.innerHTML, new RegExp(label));
  }
  assert.match(target.innerHTML, /137/);
});

test("137 ready and 6 exceptions remain distinguishable", () => {
  const target = element();
  renderDistributionSummary(target, { recipients_total: 143, contact_ready: 137, missing_contact: 6, invalid_contact: 0 }, 137);
  assert.match(target.innerHTML, /143/);
  assert.match(target.innerHTML, /137/);
  assert.match(target.innerHTML, />6</);
});

test("all READY recipients are selected by default", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /readyRecipients\(\)[\s\S]*new Set/);
  assert.match(controller, /syncSelection\(\{ reset: true \}\)/);
});

test("recipient can be deselected without rebuilding distribution", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /state\.selected\.delete\(recipientId\)/);
  assert.match(controller, /state\.selectionDirty = true/);
});

test("select all ready has a dedicated action", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftSelectAllReady"/);
  assert.match(controller, /elements\.selectAll\.addEventListener/);
});

test("missing contact is not selectable", () => {
  const target = element();
  renderDistributionRecipients(target, recipients, new Set([1]));
  assert.match(target.innerHTML, /data-select-shift-recipient="2"[\s\S]*disabled/);
  assert.match(target.innerHTML, /Contatto mancante/);
});

test("invalid contact has an explicit state", () => {
  const target = element();
  renderDistributionRecipients(target, recipients);
  assert.match(target.innerHTML, /Contatto non valido/);
  assert.match(target.innerHTML, /data-readiness="INVALID_CONTACT"/);
});

test("Da sistemare filters missing and invalid contacts", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "EXCEPTIONS").map((item) => item.id), [2, 3]);
});

test("contact exceptions deep-link back to Workforce", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftOpenWorkforce"/);
  assert.match(controller, /workspace:navigate[\s\S]*view: "workforce"/);
});

test("batch action bar reports selected count", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftBatchActions"/);
  assert.match(html, /id="driverShiftSelectedCount"/);
  assert.match(controller, /elements\.selectedCount\.textContent/);
});

test("prepare batch calls provider-agnostic backend endpoint", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /prepareDriverShiftBatch[\s\S]*prepare-batch/);
  assert.match(controller, /prepareDistributionBatch/);
});

test("prepared state says batch ready without claiming sends", async () => {
  const html = await source("index.html");
  assert.match(html, /Batch pronto/);
  assert.match(html, /Nessun messaggio è stato inviato/);
});

test("CSV export uses a real authenticated download response", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /exportDriverShiftBatchCsv[\s\S]*export\.csv/);
  assert.match(controller, /downloadBlob\(result\.blob, result\.filename\)/);
});

test("export never marks a recipient as sent", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /Nessun destinatario è stato marcato come inviato/);
  assert.doesNotMatch(controller, /delivery_status\s*=\s*["']SENT/);
});

test("acknowledgement counters remain in batch summary", () => {
  const target = element();
  renderDistributionSummary(target, { recipients_total: 4, contact_ready: 2, opened: 2, acknowledged: 1, not_opened: 2 }, 2);
  assert.match(target.innerHTML, /Visualizzati/);
  assert.match(target.innerHTML, /Presa visione/);
});

test("non-opened filter remains available", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "NOT_OPENED").map((item) => item.id), [1, 2]);
});

test("search still uses readable name", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "", "ack").map((item) => item.id), [4]);
});

test("batch UI fits 390 without fixed canvas", async () => {
  const css = await source("assets/css/driver-shift-distribution.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /driver-shift-batch-actions button[\s\S]*width: 100%/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

test("no fake WhatsApp button is rendered", async () => {
  const html = await source("index.html");
  assert.doesNotMatch(html, /Invia WhatsApp|Invia SMS|Invia email/);
  assert.match(html, /Prepara distribuzione/);
});

test("DELIVERY.1 personal fallback actions remain available", async () => {
  const presenter = await source("assets/js/modules/driver-shift-distribution-presenter.js");
  for (const action of ["data-copy-shift-link", "data-regenerate-shift-link", "data-revoke-shift-link"]) {
    assert.match(presenter, new RegExp(action));
  }
});

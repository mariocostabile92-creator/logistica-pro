import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  filterDistributionRecipients,
  renderDistributionRecipients,
  renderDistributionSummary,
  renderManualShareRecipients,
} from "../assets/js/modules/driver-shift-distribution-presenter.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "" });
const recipients = [
  { id: 1, workforce_member_id: 11, display_name: "Driver Ready", shift_days_count: 5, readiness: "READY", available_channels: ["PHONE"], access_status: "NOT_OPENED", access_revoked: false },
  { id: 2, workforce_member_id: 12, display_name: "Driver Missing", shift_days_count: 4, readiness: "MISSING_CONTACT", available_channels: [], access_status: "NOT_OPENED", access_revoked: false },
  { id: 3, workforce_member_id: 13, display_name: "Driver Invalid", shift_days_count: 3, readiness: "INVALID_CONTACT", available_channels: [], access_status: "OPENED", access_revoked: false },
  { id: 4, workforce_member_id: 14, display_name: "Driver Ack", shift_days_count: 2, readiness: "READY", available_channels: ["EMAIL"], access_status: "ACKNOWLEDGED", access_revoked: false },
];
const credentials = new Map([[11, "ACTIVE"], [12, "ACTIVE"], [13, "MISSING"], [14, "ACTIVE"]]);


test("primary summary uses credential readiness instead of contact counters", () => {
  const target = element();
  renderDistributionSummary(
    target,
    { recipients_total: 143, opened: 4, acknowledged: 2, not_opened: 139 },
    { recipients_total: 143, credentials_ready: 137 },
  );
  for (const label of ["Destinatari settimana", "Accessi pronti", "Accessi da preparare", "Visualizzati", "Presa visione"]) {
    assert.match(target.innerHTML, new RegExp(label));
  }
  assert.match(target.innerHTML, />137</);
  assert.match(target.innerHTML, />6</);
  assert.doesNotMatch(target.innerHTML, /Senza contatto|Non validi|Selezionati/);
});

test("all READY contact recipients remain selected only in legacy state", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /readyRecipients\(\)[\s\S]*new Set/);
  assert.match(controller, /renderManualShareRecipients/);
});

test("manual recipient can be deselected without rebuilding distribution", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /elements\.manualRecipients\.addEventListener\("change"/);
  assert.match(controller, /state\.selected\.delete\(recipientId\)/);
});

test("select all ready action is confined to Manual Share legacy", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftManualShare"[\s\S]*id="driverShiftSelectAllReady"/);
  assert.doesNotMatch(html, /<div class="driver-shift-selection-tools">[\s\S]*id="driverShiftDistributionRecipients"/);
});

test("primary recipient ignores missing contact when credential is active", () => {
  const target = element();
  renderDistributionRecipients(target, [recipients[1]], credentials);
  assert.match(target.innerHTML, /Accesso pronto/);
  assert.doesNotMatch(target.innerHTML, /Contatto mancante|data-select-shift-recipient/);
});

test("credential missing is explicit in primary recipient", () => {
  const target = element();
  renderDistributionRecipients(target, [recipients[2]], credentials);
  assert.match(target.innerHTML, /Accesso da preparare/);
  assert.doesNotMatch(target.innerHTML, /Contatto non valido/);
});

test("Accesso da preparare filter uses credentials", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "ACCESS_MISSING", "", credentials).map((item) => item.id), [3]);
});

test("Workforce deep-link remains secondary", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftIndividualActions"[\s\S]*id="driverShiftOpenWorkforce"/);
  assert.match(controller, /workspace:navigate[\s\S]*view: "workforce"/);
});

test("batch action bar remains inside legacy Manual Share", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftManualShare"[\s\S]*id="driverShiftBatchActions"[\s\S]*id="driverShiftSelectedCount"/);
});

test("manual renderer preserves contact-based eligibility", () => {
  const target = element();
  renderManualShareRecipients(target, recipients, new Set([1]));
  assert.match(target.innerHTML, /data-select-shift-recipient="1"[\s\S]*checked/);
  assert.match(target.innerHTML, /data-select-shift-recipient="2"[\s\S]*disabled/);
  assert.match(target.innerHTML, /Contatti non configurati/);
});

test("prepare batch still calls provider-agnostic backend endpoint", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /prepareDriverShiftBatch[\s\S]*prepare-batch/);
  assert.match(controller, /prepareDistributionBatch/);
});

test("prepared legacy state never claims automatic delivery", async () => {
  const html = await source("index.html");
  assert.match(html, /Batch pronto/);
  assert.match(html, /Nessun messaggio è stato inviato/);
});

test("CSV export remains an authenticated legacy download", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /exportDriverShiftBatchCsv[\s\S]*export\.csv/);
  assert.match(controller, /downloadBlob\(result\.blob, result\.filename\)/);
});

test("export never marks a recipient as sent", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /Nessun destinatario Ã¨ stato marcato come inviato|Nessun destinatario è stato marcato come inviato/);
  assert.doesNotMatch(controller, /delivery_status\s*=\s*["']SENT/);
});

test("reading counters stay in the primary summary", () => {
  const target = element();
  renderDistributionSummary(target, { recipients_total: 4, opened: 2, acknowledged: 1, not_opened: 2 }, { recipients_total: 4, credentials_ready: 2 });
  assert.match(target.innerHTML, /Visualizzati/);
  assert.match(target.innerHTML, /Presa visione/);
});

test("non-opened filter remains available", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "NOT_OPENED", "", credentials).map((item) => item.id), [1, 2]);
});

test("search still uses readable name", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "", "ack", credentials).map((item) => item.id), [4]);
});

test("legacy batch UI fits 390 without fixed canvas", async () => {
  const css = await source("assets/css/driver-shift-distribution.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /driver-shift-batch-actions button[\s\S]*width: 100%/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

test("no fake send action is rendered", async () => {
  const html = await source("index.html");
  assert.doesNotMatch(html, /Invia WhatsApp|Invia SMS|Invia email/);
  assert.match(html, /Copia messaggio per il gruppo WhatsApp/);
});

test("personal fallback actions remain available inside support details", async () => {
  const presenter = await source("assets/js/modules/driver-shift-distribution-presenter.js");
  assert.match(presenter, /driver-shift-recipient-support/);
  for (const action of ["data-copy-shift-link", "data-regenerate-shift-link", "data-revoke-shift-link"]) {
    assert.match(presenter, new RegExp(action));
  }
});

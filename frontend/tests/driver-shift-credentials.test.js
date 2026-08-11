import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  credentialStatusMap,
  renderCredentialSummary,
  renderInitialCredentials,
} from "../assets/js/modules/driver-shift-credentials-presenter.js";
import { initialCredentialCsv } from "../assets/js/modules/driver-shift-credentials.js";
import { renderDistributionRecipients } from "../assets/js/modules/driver-shift-distribution-presenter.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "", hidden: false });
const model = {
  distribution_id: 7,
  summary: {
    recipients_total: 200, credentials_ready: 187, already_existing: 187,
    newly_created: 0, revoked: 0, reset_required: 0, missing: 13, errors: 0,
  },
  recipients: [
    { workforce_member_id: 10, display_name: "Mario Rossi", credential_status: "ACTIVE" },
    { workforce_member_id: 11, display_name: "Anna Verdi", credential_status: null },
  ],
};


test("credential readiness renders ready and missing counts", () => {
  const target = element();
  renderCredentialSummary(target, model);
  assert.match(target.innerHTML, /Accessi pronti: 187\/200/);
  assert.match(target.innerHTML, /13 accessi da preparare/);
});


test("prepare CTA uses the missing recipient count", () => {
  const target = element();
  renderCredentialSummary(target, model);
  assert.match(target.innerHTML, /data-prepare-driver-credentials/);
  assert.match(target.innerHTML, /Prepara 13 accessi/);
});


test("all-ready state does not ask for weekly onboarding", () => {
  const target = element();
  renderCredentialSummary(target, {
    ...model,
    summary: { ...model.summary, credentials_ready: 200, already_existing: 200, missing: 0 },
  });
  assert.match(target.innerHTML, /Tutti i driver della settimana hanno un accesso personale/);
  assert.doesNotMatch(target.innerHTML, /Prepara 200/);
});


test("one-time created state exposes warning and download only while raw values exist", () => {
  const target = element();
  renderInitialCredentials(target, [
    { display_name: "Mario Rossi", access_code: "AB7K4P2Q", initial_pin: "123456" },
  ]);
  assert.equal(target.hidden, false);
  assert.match(target.innerHTML, /una sola volta/);
  assert.match(target.innerHTML, /data-download-initial-credentials/);
  renderInitialCredentials(target, []);
  assert.equal(target.hidden, true);
  assert.doesNotMatch(target.innerHTML, /123456/);
});


test("initial enrollment CSV contains only required fields and blocks formulas", () => {
  const csv = initialCredentialCsv([
    { display_name: "=HYPERLINK(1)", access_code: "AB7K4P2Q", initial_pin: "123456" },
  ]);
  assert.match(csv, /Driver,Access Code,PIN iniziale/);
  assert.match(csv, /'\=HYPERLINK/);
  assert.doesNotMatch(csv, /workforce_member_id|phone|email|shift|quality/i);
});


test("recipient credential status is shown without exposing PIN or access code", () => {
  const target = element();
  const statuses = credentialStatusMap(model);
  renderDistributionRecipients(target, [{
    id: 1, workforce_member_id: 10, display_name: "Mario Rossi", shift_days_count: 5,
    readiness: "READY", available_channels: [], access_status: "NOT_OPENED", access_revoked: false,
  }], new Set(), statuses);
  assert.match(target.innerHTML, /Accesso pronto/);
  assert.match(target.innerHTML, /data-reset-driver-credential="10"/);
  assert.match(target.innerHTML, /data-revoke-driver-credential="10"/);
  assert.doesNotMatch(target.innerHTML, /123456|AB7K4P2Q/);
});


test("controller clears one-time raw output before every refresh", async () => {
  const controller = await source("assets/js/modules/driver-shift-credentials.js");
  assert.match(controller, /async function load\(\)[\s\S]*state\.initial = \[\]/);
  assert.match(controller, /second|Nessuna nuova credenziale/i);
});


test("reset and revoke use dedicated admin actions", async () => {
  const [api, controller] = await Promise.all([
    source("assets/js/api.js"), source("assets/js/modules/driver-shift-credentials.js"),
  ]);
  assert.match(api, /resetDriverShiftCredential/);
  assert.match(api, /revokeDriverShiftCredential/);
  assert.match(controller, /credentialsController|resetCredential/);
  assert.match(controller, /revokeCredential/);
});


test("credential UI is loaded inside the existing Accesso driver section", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"), source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /id="driverShiftCredentials"/);
  assert.match(html, /id="driverShiftInitialCredentials"/);
  assert.match(controller, /initDriverShiftCredentials/);
});


test("credential layout fits 390px without a fixed canvas", async () => {
  const css = await source("assets/css/driver-shift-credentials.css");
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /min-width: 0/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

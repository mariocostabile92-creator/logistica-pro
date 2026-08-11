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
  { id: 1, display_name: "Mario Rossi", shift_days_count: 6, access_status: "NOT_OPENED", access_revoked: false },
  { id: 2, display_name: "Yassine Zyadi", shift_days_count: 5, access_status: "OPENED", access_revoked: false },
  { id: 3, display_name: "Anna Verdi", shift_days_count: 4, access_status: "ACKNOWLEDGED", access_revoked: false },
];


test("Distribuisci turni is the ACTIVE planning entry point", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftDistributeBtn"[^>]*>Distribuisci turni/);
  assert.match(controller, /planning\?\.status !== "ACTIVE"/);
});

test("DRAFT planning hides delivery instead of generating manual recipients", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /elements\.entry\.hidden = planning\?\.status !== "ACTIVE"/);
  assert.doesNotMatch(controller, /selectDriver|selectedDriver|workforce_member_id/);
});

test("prepare distribution is an explicit admin action", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /prepareDriverShiftDistribution[\s\S]*method: "POST"/);
  assert.match(controller, /elements\.entry\.addEventListener\("click", openWindowDialog\)/);
  assert.match(controller, /elements\.windowConfirm\.addEventListener\("click", \(\) => void prepare\(\)\)/);
});

test("distribution summary exposes recipients readiness opens and acknowledgements", () => {
  const target = element();
  renderDistributionSummary(target, { recipients_total: 143, ready: 143, opened: 2, acknowledged: 1, not_opened: 141 });
  for (const value of ["Destinatari", "Pronti", "Visualizzati", "Presa visione", "Non visualizzati", "143"]) assert.match(target.innerHTML, new RegExp(value));
});

test("recipient list stays compact and day-count based", () => {
  const target = element();
  renderDistributionRecipients(target, recipients);
  assert.match(target.innerHTML, /Mario Rossi/);
  assert.match(target.innerHTML, /6 giornate/);
  assert.doesNotMatch(target.innerHTML, /T-ID|transporter/);
});

test("recipient status filters are exact", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "OPENED").map((item) => item.id), [2]);
  assert.deepEqual(filterDistributionRecipients(recipients, "ACKNOWLEDGED").map((item) => item.id), [3]);
});

test("recipient search uses readable driver name", () => {
  assert.deepEqual(filterDistributionRecipients(recipients, "", "yassine").map((item) => item.id), [2]);
});

test("manual share retrieves one access link then copies it", async () => {
  const [api, controller] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(api, /getDriverShiftRecipientAccessLink/);
  assert.match(controller, /getRecipientAccessLink[\s\S]*copyText\(link\.access_url\)/);
  assert.doesNotMatch(api, /distribution[\s\S]*tokens/);
});

test("recipient access supports explicit revoke and regenerate", async () => {
  const [api, presenter] = await Promise.all([source("assets/js/api.js"), source("assets/js/modules/driver-shift-distribution-presenter.js")]);
  assert.match(api, /revokeDriverShiftRecipientAccess/);
  assert.match(api, /regenerateDriverShiftRecipientAccess/);
  assert.match(presenter, /data-regenerate-shift-link/);
  assert.match(presenter, /data-revoke-shift-link/);
});

test("admin can refresh delivery statuses without reloading the workspace", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftDistributionRefresh"/);
  assert.match(controller, /elements\.refresh\.addEventListener\("click", \(\) => load\(\)\)/);
  assert.doesNotMatch(controller, /location\.reload/);
});

test("public page has a finite loading content and invalid-link state", async () => {
  const html = await source("driver-shifts/index.html");
  assert.match(html, /driverShiftsLoading/);
  assert.match(html, /driverShiftsContent/);
  assert.match(html, /Link non disponibile/);
});

test("public page renders the readable driver name", async () => {
  const [html, script] = await Promise.all([source("driver-shifts/index.html"), source("assets/js/driver-shifts-public.js")]);
  assert.match(html, /id="driverShiftsDriver"/);
  assert.match(script, /model\.driver_name/);
});

test("public page renders chronological personal shifts from the backend order", async () => {
  const script = await source("assets/js/driver-shifts-public.js");
  assert.match(script, /model\.shifts\.map\(renderShift\)/);
  assert.doesNotMatch(script, /workforce_member_id|transporter_id|provenance/);
});

test("rest day has an explicit readable state", async () => {
  const script = await source("assets/js/driver-shifts-public.js");
  assert.match(script, /shift\.availability \? "Programmato" : "Riposo"/);
});

test("station is visible only as a safe operational field", async () => {
  const script = await source("assets/js/driver-shifts-public.js");
  assert.match(script, /fact\("Station", shift\.station/);
});

test("acknowledgement says Ho visto and uses the dedicated endpoint", async () => {
  const [html, script] = await Promise.all([source("driver-shifts/index.html"), source("assets/js/driver-shifts-public.js")]);
  assert.match(html, /Ho visto i turni/);
  assert.match(script, /\/acknowledge/);
  assert.doesNotMatch(`${html}${script}`, /Accetto il turno/);
});

test("acknowledged state is idempotent presentation", async () => {
  const script = await source("assets/js/driver-shifts-public.js");
  assert.match(script, /access_status === "ACKNOWLEDGED"/);
  assert.match(script, /Presa visione registrata/);
});

test("invalid revoked or expired links share one safe public error", async () => {
  const script = await source("assets/js/driver-shifts-public.js");
  assert.match(script, /if \(!response\.ok\) throw new Error\("DRIVER_SHIFTS_NOT_AVAILABLE"\)/);
  assert.match(script, /catch \{ showError\(\); \}/);
});

test("public mobile page has no administrative navigation", async () => {
  const html = await source("driver-shifts/index.html");
  assert.doesNotMatch(html, /workspace-tabs|Fleet|Planning|Workforce|Logout/);
});

test("public and admin delivery layouts fit 390px without a fixed canvas", async () => {
  const [publicCss, adminCss] = await Promise.all([
    source("assets/css/driver-shifts-public.css"),
    source("assets/css/driver-shift-distribution.css"),
  ]);
  assert.match(publicCss, /@media \(max-width: 430px\)/);
  assert.match(adminCss, /@media \(max-width: 520px\)/);
  assert.doesNotMatch(`${publicCss}${adminCss}`, /width:\s*(?:390|768|1440)px/);
  assert.match(adminCss, /min-height: 44px/);
});

test("public requests omit cookies and shared cache", async () => {
  const [script, html] = await Promise.all([source("assets/js/driver-shifts-public.js"), source("driver-shifts/index.html")]);
  assert.match(script, /credentials: "omit"/);
  assert.match(script, /cache: "no-store"/);
  assert.match(html, /noindex,nofollow,noarchive/);
});

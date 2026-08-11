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
const noContactRecipient = {
  id: 1, workforce_member_id: 101, display_name: "Mario Rossi", shift_days_count: 6,
  readiness: "MISSING_CONTACT", available_channels: [], access_status: "NOT_OPENED", access_revoked: false,
};
const credentialReady = new Map([[101, "ACTIVE"]]);


test("shared mode primary recipient hides selection checkbox", () => {
  const target = element();
  renderDistributionRecipients(target, [noContactRecipient], credentialReady);
  assert.doesNotMatch(target.innerHTML, /type="checkbox"|data-select-shift-recipient/);
});

test("select-all control exists only below Manual Share legacy", async () => {
  const html = await source("index.html");
  assert.match(html, /id="driverShiftManualShare"[\s\S]*id="driverShiftSelectAllReady"/);
  assert.doesNotMatch(html.slice(html.indexOf("driverShiftDistributionRecipients"), html.indexOf("driverShiftIndividualActions")), /Seleziona tutti/);
});

test("missing phone does not block shared primary readiness", () => {
  const target = element();
  renderDistributionRecipients(target, [noContactRecipient], credentialReady);
  assert.match(target.innerHTML, /Accesso pronto/);
  assert.doesNotMatch(target.innerHTML, /Contatto mancante|Nessun canale/);
});

test("credential status drives primary readiness", () => {
  const target = element();
  renderDistributionRecipients(target, [noContactRecipient], new Map([[101, "MISSING"]]));
  assert.match(target.innerHTML, /Accesso da preparare/);
});

test("primary summary uses Accessi pronti", () => {
  const target = element();
  renderDistributionSummary(target, { recipients_total: 142 }, { recipients_total: 142, credentials_ready: 142 });
  assert.match(target.innerHTML, /Accessi pronti[\s\S]*142/);
  assert.match(target.innerHTML, /Accessi da preparare[\s\S]*0/);
});

test("missing credential warning and action use credential count", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /driver non hanno ancora un accesso personale/);
  assert.match(controller, /`Prepara \$\{Number\(credentialSummary\?\.missing \|\| 0\)\} accessi`/);
});

test("all-ready state is explicit", async () => {
  const [controller, presenter] = await Promise.all([
    source("assets/js/modules/driver-shift-distribution.js"),
    source("assets/js/modules/driver-shift-credentials-presenter.js"),
  ]);
  assert.match(controller, /Tutti i driver della settimana hanno un accesso personale/);
  assert.match(presenter, /Tutti i driver della settimana hanno un accesso personale/);
});

test("WhatsApp CTA depends on ready credentials, not contacts", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /elements\.groupCopy\.disabled = !credentialSummary \|\| ready === 0/);
  const groupFlow = controller.slice(controller.indexOf("function renderGroupShare"), controller.indexOf("function groupMessage"));
  assert.doesNotMatch(groupFlow, /phone|email|contact_ready|missing_contact/);
});

test("personal link is a secondary support action", () => {
  const target = element();
  renderDistributionRecipients(target, [noContactRecipient], credentialReady);
  assert.match(target.innerHTML, /<details class="driver-shift-recipient-support">/);
  assert.match(target.innerHTML, />Link personale</);
  assert.match(target.innerHTML, /solo se il driver non riesce ad accedere dal link condiviso/);
});

test("primary filters are access and reading based", async () => {
  const html = await source("index.html");
  for (const label of ["Tutti", "Accesso da preparare", "Non visualizzati", "Visualizzati", "Presa visione"]) assert.match(html, new RegExp(`>${label}<`));
  assert.doesNotMatch(html, /data-distribution-filter="READY"|data-distribution-filter="EXCEPTIONS"/);
  assert.equal(filterDistributionRecipients([noContactRecipient], "ACCESS_MISSING", "", credentialReady).length, 0);
});

test("selected week is always visible in distribution and group block", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /id="driverShiftDistributionWeekContext"/);
  assert.match(html, /id="driverShiftGroupPeriod"/);
  assert.match(controller, /Settimana: \$\{week\}/);
});

test("tracking is a distinct semantic block", async () => {
  const [html, controller] = await Promise.all([source("index.html"), source("assets/js/modules/driver-shift-distribution.js")]);
  assert.match(html, /Stato lettura[\s\S]*id="driverShiftTrackingSummary"/);
  assert.match(controller, /renderMetricSummary\(elements\.trackingSummary/);
});

test("individual actions are secondary and collapsible", async () => {
  const html = await source("index.html");
  assert.match(html, /<details id="driverShiftIndividualActions"[\s\S]*<summary>Azioni individuali<\/summary>/);
});

test("manual share regression remains available in its own renderer", () => {
  const target = element();
  renderManualShareRecipients(target, [noContactRecipient], new Set());
  assert.match(target.innerHTML, /data-select-shift-recipient="1"/);
  assert.match(target.innerHTML, /Contatti non configurati/);
});

test("390 layout has full-width CTA and no fixed viewport canvas", async () => {
  const css = await source("assets/css/driver-shift-distribution.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /#driverShiftGroupMessageCopy\s*{[\s\S]*width:\s*100%/);
  assert.match(css, /driver-shift-recipient-actions button\s*{\s*width:\s*100%/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});

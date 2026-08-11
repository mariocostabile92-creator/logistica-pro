import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { renderWorkforceContactCoverage } from "../assets/js/modules/workforce-contact-coverage.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const element = () => ({ innerHTML: "" });


test("import preview exposes phone email and invalid contact counts", async () => {
  const view = await source("assets/js/modules/workforce-view.js");
  assert.match(view, /Telefono rilevato/);
  assert.match(view, /Email rilevate/);
  assert.match(view, /Contatti invalidi/);
  assert.match(view, /preview\.phone_detected/);
  assert.match(view, /preview\.email_detected/);
  assert.match(view, /preview\.invalid_contacts/);
});


test("invalid contact warnings remain in the import issue surface", async () => {
  const view = await source("assets/js/modules/workforce-view.js");
  assert.match(view, /const anomalies = Array\.isArray\(preview\.anomalies\)/);
  assert.match(view, /workforceImportIssuesList/);
  assert.match(view, /Contatti invalidi/);
});


test("Workforce detail keeps phone and email visible and editable", async () => {
  const [detail, page, html] = await Promise.all([
    source("assets/js/modules/workforce-detail-panel.js"),
    source("assets/js/modules/workforce-page.js"),
    source("index.html"),
  ]);
  assert.match(detail, /workforceMemberDetailPhone/);
  assert.match(detail, /workforceMemberDetailEmail/);
  assert.match(page, /phone: byId\("workforceMemberPhone"\)/);
  assert.match(page, /email: byId\("workforceMemberEmail"\)/);
  assert.match(html, /id="workforceMemberPhone"/);
  assert.match(html, /id="workforceMemberEmail"/);
});


test("coverage widget renders member contact metrics", () => {
  const target = element();
  renderWorkforceContactCoverage(target, {
    total_members: 10, active_members: 9, phone_valid: 8, phone_invalid: 1,
    email_valid: 5, email_invalid: 1, both_valid: 4, no_channel: 1,
    active_planning_available: false,
  });
  for (const label of ["Copertura contatti", "Telefono validi", "Email valide", "Senza canale"]) {
    assert.match(target.innerHTML, new RegExp(label));
  }
  assert.match(target.innerHTML, /9 membri attivi su 10/);
});


test("coverage widget shows no ACTIVE planning without invented metrics", () => {
  const target = element();
  renderWorkforceContactCoverage(target, {
    total_members: 10, active_members: 10, active_planning_available: false,
  });
  assert.match(target.innerHTML, /Nessun planning ACTIVE/);
  assert.match(target.innerHTML, /dopo la pubblicazione dei turni/);
  assert.doesNotMatch(target.innerHTML, /Planning ACTIVE #/);
});


test("ACTIVE planning coverage renders real recipient metrics", () => {
  const target = element();
  renderWorkforceContactCoverage(target, {
    total_members: 10, active_members: 10, phone_valid: 8, email_valid: 5,
    both_valid: 4, no_channel: 1, active_planning_available: true,
    active_planning_id: 7, recipients_total: 10, recipients_phone_ready: 8,
    recipients_email_ready: 5, recipients_both: 4, recipients_no_channel: 1,
  });
  assert.match(target.innerHTML, /Planning ACTIVE #7/);
  assert.match(target.innerHTML, /Copertura destinatari reali/);
  for (const value of ["Destinatari", "Telefono", "Email", "Entrambi", "Senza canale"]) {
    assert.match(target.innerHTML, new RegExp(value));
  }
});


test("Workforce refresh loads coverage and Delivery remains derived", async () => {
  const [page, api, distribution] = await Promise.all([
    source("assets/js/modules/workforce-page.js"),
    source("assets/js/api.js"),
    source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(api, /getWorkforceContactCoverage[\s\S]*contact-coverage/);
  assert.match(page, /getWorkforceContactCoverage\(\)/);
  assert.match(page, /renderWorkforceContactCoverage/);
  assert.match(distribution, /async function load/);
  assert.match(distribution, /getDistribution\(state\.planning\.id\)/);
  const setPlanning = distribution.slice(distribution.indexOf("setPlanning(planning)"));
  assert.doesNotMatch(setPlanning, /load\(\{ quietMissing: true \}\)/);
  assert.match(distribution, /windowConfirm\.addEventListener[\s\S]*void prepare\(\)/);
});


test("contact coverage remains fluid at 390 px", async () => {
  const css = await source("assets/css/workforce-contact-coverage.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /min-width: 0/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

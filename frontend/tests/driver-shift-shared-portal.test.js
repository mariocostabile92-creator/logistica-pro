import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("ACTIVE distribution exposes one shared access portal section", async () => {
  const [html, controller] = await Promise.all([
    source("index.html"),
    source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(html, /id="driverShiftPortal"/);
  assert.match(html, /Shared Portal/);
  assert.match(html, /Condividi un unico link nel gruppo\. Ogni driver vedrÃ  soltanto i propri turni\.|Condividi un unico link nel gruppo\. Ogni driver vedrà soltanto i propri turni\./);
  assert.match(controller, /getSharedPortal/);
  assert.match(controller, /prepareSharedPortal/);
});


test("shared portal copy uses one returned access URL", async () => {
  const controller = await source("assets/js/modules/driver-shift-distribution.js");
  assert.match(controller, /copyText\(state\.portal\.access_url\)/);
  assert.match(controller, /Link condiviso copiato/);
  assert.doesNotMatch(controller, /state\.portal\.recipients|state\.portal\.driver/);
});


test("shared portal supports explicit revoke and regenerate", async () => {
  const [api, html, controller] = await Promise.all([
    source("assets/js/api.js"), source("index.html"),
    source("assets/js/modules/driver-shift-distribution.js"),
  ]);
  assert.match(api, /getDriverShiftPortal/);
  assert.match(api, /prepareDriverShiftPortal/);
  assert.match(api, /revokeDriverShiftPortal/);
  assert.match(api, /regenerateDriverShiftPortal/);
  assert.match(html, /id="driverShiftPortalRevoke"/);
  assert.match(html, /id="driverShiftPortalRegenerate"/);
  assert.match(controller, /revokeSharedPortal/);
  assert.match(controller, /regenerateSharedPortal/);
});


test("public landing contains shared login and no embedded driver data", async () => {
  const html = await source("driver-shifts/access/index.html");
  assert.match(html, /I tuoi turni/);
  assert.match(html, /Codice di accesso/);
  assert.match(html, /Ricordami su questo dispositivo/);
  for (const forbidden of ["driver_name", "recipient", "station", "organization_id", "workforce_member_id"])
    assert.doesNotMatch(html, new RegExp(forbidden, "i"));
});


test("public token stays in fragment and validation omits credentials and cache", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /location\.hash/);
  assert.match(script, /\/api\/public\/driver-shifts\/access\/validate/);
  assert.match(script, /credentials: "omit"/);
  assert.match(script, /cache: "no-store"/);
  assert.match(script, /body: JSON\.stringify\(\{ token \}\)/);
  assert.doesNotMatch(script, /localStorage|sessionStorage|document\.cookie/);
});


test("public landing uses a generic invalid-link state", async () => {
  const [html, script] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/js/driver-shifts-access.js"),
  ]);
  assert.match(html, /Link non disponibile/);
  assert.match(script, /if \(!response\.ok\) throw new Error/);
  assert.doesNotMatch(`${html}${script}`, /credential revoked|session expired|distribution superseded/i);
});


test("shared portal layouts fit mobile without fixed canvas", async () => {
  const [adminCss, publicCss] = await Promise.all([
    source("assets/css/driver-shift-distribution.css"),
    source("assets/css/driver-shifts-access.css"),
  ]);
  assert.match(adminCss, /@media \(max-width: 520px\)/);
  assert.match(publicCss, /@media \(max-width: 430px\)/);
  assert.match(adminCss, /min-height: 44px/);
  assert.doesNotMatch(`${adminCss}${publicCss}`, /width:\s*(?:390|768|1440)px/);
});


test("shared portal remains separate from existing personal access links", async () => {
  const [shared, personal] = await Promise.all([
    source("assets/js/driver-shifts-access.js"),
    source("assets/js/driver-shifts-public.js"),
  ]);
  assert.match(shared, /access\/validate/);
  assert.match(shared, /portal\/login/);
  assert.match(personal, /\/api\/public\/driver-shifts\/\$\{encodeURIComponent\(token\)\}/);
  assert.match(personal, /acknowledge/);
});

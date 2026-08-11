import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("shared login asks only for code, PIN, and optional persistence", async () => {
  const html = await source("driver-shifts/access/index.html");
  assert.match(html, /id="driverShiftsAccessCode"/);
  assert.match(html, /id="driverShiftsPin"/);
  assert.match(html, /id="driverShiftsRemember"/);
  assert.match(html, /type="password"/);
  for (const forbidden of ["T-ID", "workforce_member_id", "organization_id", "Nome driver"])
    assert.doesNotMatch(html, new RegExp(forbidden, "i"));
});


test("login sends fragment token without browser storage", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /portal_token: tokenFromFragment\(\)/);
  assert.match(script, /access_code:/);
  assert.match(script, /remember_device:/);
  assert.match(script, /credentials: "include"/);
  assert.doesNotMatch(script, /localStorage|sessionStorage|document\.cookie/);
});


test("invalid login uses one generic public error", async () => {
  const [html, script] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/js/driver-shifts-access.js"),
  ]);
  assert.match(html, /Dati di accesso non validi\./);
  assert.match(script, /DRIVER_SHIFT_LOGIN_INVALID/);
  assert.doesNotMatch(`${html}${script}`, /codice inesistente|pin errato|non destinatario/i);
});


test("successful access renders only safe session fields", async () => {
  const [html, script] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/js/driver-shifts-access.js"),
  ]);
  assert.match(html, /id="driverShiftsAccessSuccess"/);
  assert.match(script, /session\.driver_name/);
  assert.match(script, /session\.period_start/);
  assert.match(script, /session\.period_end/);
  assert.match(script, /\/api\/public\/driver-shifts\/me/);
  assert.doesNotMatch(script, /session\.organization|session\.workforce|session\.credential/);
});


test("logout is explicit and returns to portal login", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /\/api\/public\/driver-shifts\/logout/);
  assert.match(script, /logout\.addEventListener/);
  assert.match(script, /await validatePortal\(\)/);
});


test("expired sessions fall back to generic portal validation", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /if \(await currentSession\(\)\) return/);
  assert.match(script, /await validatePortal\(\)/);
  assert.doesNotMatch(script, /credential revoked|session expired|distribution superseded/i);
});


test("shared login UI is mobile-safe and has no fixed viewport canvas", async () => {
  const css = await source("assets/css/driver-shifts-access.css");
  assert.match(css, /@media \(max-width: 430px\)/);
  assert.match(css, /width: min\(100%, 31rem\)/);
  assert.match(css, /overflow: hidden/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});


test("personal driver access implementation remains independent", async () => {
  const [shared, personal] = await Promise.all([
    source("assets/js/driver-shifts-access.js"), source("assets/js/driver-shifts-public.js"),
  ]);
  assert.match(shared, /portal\/login/);
  assert.match(personal, /acknowledge/);
  assert.doesNotMatch(personal, /portal\/login/);
});

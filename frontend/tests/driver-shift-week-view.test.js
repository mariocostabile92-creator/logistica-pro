import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { formatShiftPeriod } from "../assets/js/driver-shifts-week.js";


const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("valid remembered sessions try the private week before the portal", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  const initialize = script.slice(script.indexOf("async function initialize"));
  assert.ok(initialize.indexOf("await loadWeek({ initial: true })") < initialize.indexOf("await validatePortal()"));
});


test("week view uses only the session-scoped endpoint", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /fetch\("\/api\/public\/driver-shifts\/me\/shifts"/);
  assert.doesNotMatch(script, /me\/shifts\?organization|me\/shifts\?driver|workforce_member_id/);
});


test("week requests include cookies and explicitly bypass caches", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /credentials: "include"/);
  assert.match(script, /cache: "no-store"/);
});


test("driver and period have dedicated safe text targets", async () => {
  const [html, script] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/js/driver-shifts-access.js"),
  ]);
  assert.match(html, /id="driverShiftsDriverName"/);
  assert.match(html, /id="driverShiftsPeriod"/);
  assert.match(script, /driverName\.textContent = week\.driver_name/);
  assert.match(script, /period\.textContent = formatShiftPeriod/);
});


test("period formatting is deterministic and local-date safe", () => {
  assert.equal(formatShiftPeriod("2026-08-17", "2026-08-23"), "17–23 agosto");
  assert.equal(formatShiftPeriod("2026-08-31", "2026-09-06"), "31 agosto – 6 settembre");
});


test("the presenter renders every day returned by the backend", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /week\.days\.forEach/);
  assert.match(presenter, /day\.operational_date/);
  assert.match(presenter, /day\.date_label/);
});


test("multiple shifts on one date are never collapsed", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /day\.shifts\.forEach/);
  assert.match(presenter, /entries\.append\(renderShift/);
  assert.doesNotMatch(presenter, /day\.shifts\[0\]/);
});


test("shift codes use the backend display label without client reinterpretation", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /shift\.display_label/);
  assert.doesNotMatch(presenter, /case\s+["']R["']|SHIFT_LABELS|codeMap/);
});


test("missing days keep the explicit unavailable label", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /Turno non disponibile/);
  assert.match(presenter, /day\.missing/);
  assert.doesNotMatch(presenter, /missing.*Riposo/i);
});


test("time ranges and stations are visible when supplied", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /shift\.start_time \|\| shift\.end_time/);
  assert.match(presenter, /shift\.station/);
  assert.match(presenter, /driver-shift-time/);
  assert.match(presenter, /driver-shift-station/);
});


test("rendering uses textContent and contains no HTML injection sink", async () => {
  const presenter = await source("assets/js/driver-shifts-week.js");
  assert.match(presenter, /element\.textContent = text/);
  assert.doesNotMatch(presenter, /innerHTML|insertAdjacentHTML|outerHTML/);
});


test("the acknowledgement action has clear Italian copy", async () => {
  const html = await source("driver-shifts/access/index.html");
  assert.match(html, /Ho visto i turni/);
  assert.match(html, /Conferma soltanto la presa visione dei turni/);
  assert.match(html, /Presa visione registrata/);
});


test("acknowledgement posts only through the current private session", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /fetch\("\/api\/public\/driver-shifts\/me\/acknowledge"/);
  assert.match(script, /method: "POST"/);
  assert.doesNotMatch(script, /acknowledge[^]*organization_id|acknowledge[^]*distribution_id/);
});


test("an acknowledged week hides the CTA and retains confirmation", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /ackResult\.hidden = !week\.acknowledged/);
  assert.match(script, /acknowledge\.hidden = week\.acknowledged/);
});


test("loading and retry states use polite or alert live regions", async () => {
  const html = await source("driver-shifts/access/index.html");
  assert.match(html, /id="driverShiftsWeekStatus"[^>]+aria-live="polite"/);
  assert.match(html, /id="driverShiftsWeekError"[^>]+role="alert"/);
  assert.match(html, /id="driverShiftsWeekRetry"/);
});


test("network failure does not erase the authenticated week shell", async () => {
  const script = await source("assets/js/driver-shifts-access.js");
  assert.match(script, /function showWeekFailure\(\)[^]*show\(success\)/);
  assert.match(script, /Impossibile registrare la presa visione\. Riprova\./);
});


test("logout remains available but visually secondary", async () => {
  const [html, css] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/css/driver-shifts-access.css"),
  ]);
  assert.match(html, /id="driverShiftsLogout"[^>]+driver-shifts-logout/);
  assert.match(css, /\.driver-shifts-logout\s*{[^}]*background:\s*transparent/s);
});


test("mobile 390 layout is single-column and overflow safe", async () => {
  const css = await source("assets/css/driver-shifts-access.css");
  assert.match(css, /@media \(max-width: 430px\)/);
  assert.match(css, /\.driver-shift-entry\s*{\s*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(css, /\.driver-shifts-access-card\s*{[^}]*overflow:\s*hidden/s);
  assert.match(css, /overflow-wrap:\s*anywhere/);
});


test("all principal touch controls meet the 44px target", async () => {
  const css = await source("assets/css/driver-shifts-access.css");
  assert.match(css, /\.driver-shifts-ack button\s*{[^}]*min-height:\s*3rem/s);
  assert.match(css, /\.driver-shifts-logout\s*{[^}]*min-height:\s*44px/s);
  assert.match(css, /\.driver-shifts-access-secondary\s*{[^}]*min-height:\s*3rem/s);
});


test("no private payload is exposed through browser storage or globals", async () => {
  const scripts = await Promise.all([
    source("assets/js/driver-shifts-access.js"), source("assets/js/driver-shifts-week.js"),
  ]);
  const combined = scripts.join("\n");
  assert.doesNotMatch(combined, /localStorage|sessionStorage|window\.[A-Za-z_$].*=|document\.cookie/);
  assert.doesNotMatch(combined, /transporter_id|organization_id|workforce_member_id|provenance/);
});


test("the driver page contains no administrative controls", async () => {
  const html = await source("driver-shifts/access/index.html");
  assert.doesNotMatch(
    html,
    /Distribuisci|Prepara credenziali|Rigenera portale|Destinatari|Stato consegne/i,
  );
});


test("the private view does not register a service worker", async () => {
  const [html, script] = await Promise.all([
    source("driver-shifts/access/index.html"), source("assets/js/driver-shifts-access.js"),
  ]);
  assert.doesNotMatch(`${html}\n${script}`, /serviceWorker|navigator\.serviceWorker/);
  assert.match(html, /noindex,nofollow,noarchive/);
});

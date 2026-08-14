import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("organization diagnostics exposes all explicit maintenance scopes", async () => {
  const html = await file("index.html");
  for (const value of [
    "Diagnostica",
    "Genera token manutenzione",
    "Planning Coverage Backfill",
    "Workforce Operational Cycle Backfill",
    "Planning Forecast Template Reconciliation",
    "15 minuti",
    "30 minuti",
    "Copia token",
    "Questo token concede accesso tecnico limitato fino alla scadenza",
    "Token mostrato una sola volta",
  ]) assert.match(html, new RegExp(value, "i"));
  assert.match(html, /value="PLANNING_COVERAGE_BACKFILL"/);
  assert.match(html, /value="WORKFORCE_OPERATIONAL_CYCLE_BACKFILL"/);
  assert.match(html, /value="PLANNING_FORECAST_TEMPLATE_RECONCILIATION"/);
  assert.doesNotMatch(html, /value="\*"/);
});

test("maintenance token creation uses the admin endpoint and never browser storage", async () => {
  const [api, controller] = await Promise.all([
    file("assets/js/organization/api.js"),
    file("assets/js/organization/index.js"),
  ]);
  assert.match(api, /POST/);
  assert.match(api, /\/api\/admin\/maintenance-tokens/);
  assert.match(controller, /created\.token/);
  assert.match(controller, /created\.expires_at/);
  assert.match(controller, /navigator\.clipboard\.writeText/);
  assert.doesNotMatch(`${api}\n${controller}`, /localStorage|sessionStorage|indexedDB/);
});

test("maintenance diagnostics remains usable at 390px", async () => {
  const css = await file("assets/css/maintenance-token.css");
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /min-height: 44px/);
  assert.match(css, /grid-template-columns: 1fr/);
  assert.match(css, /overflow-wrap: anywhere/);
  assert.doesNotMatch(css, /width:\s*390px/);
});

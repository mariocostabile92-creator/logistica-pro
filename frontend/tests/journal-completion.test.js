import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { completionCard } from "../assets/js/modules/journal-control-room/completion-card.js";
import { completionKpis } from "../assets/js/modules/journal-control-room/completion-kpi.js";
import { journalCompletionSection } from "../assets/js/modules/journal-control-room/completion-section.js";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const completion = {
  planning_id: 42,
  operational_date: "2026-08-02",
  drivers_expected: 78,
  check_out: { expected: 78, completed: 76, missing: 2 },
  check_in: { expected: 78, completed: 72, missing: 6 },
  procedures: { open: 1, in_progress: 1, late: 2, anomalies: 3 },
  exceptions: [{ reason: "route_cancelled" }],
  missing: [{
    driver_name: "Mario Rossi", driver_id: "DRV-077", plate: "AB123CD",
    vehicle_model: "Furgone", planning_id: 42, procedure_label: "Rientro",
    expected_time: "18:00", delay_label: "2h 15m", status: "critico",
    procedure_id: null,
  }],
};

test("Journal Completion renders the exact QA truth set as real filters", () => {
  const html = completionKpis(completion, "checkin_missing");
  for (const value of ["78", "76", "72", "2", "6", "3"])
    assert.match(html, new RegExp(`>${value}<`));
  for (const filter of ["drivers_expected", "checkout_expected", "checkout_completed",
    "checkout_missing", "checkin_expected", "checkin_completed", "checkin_missing",
    "procedures_open", "procedures_in_progress", "procedures_late", "procedures_anomaly"])
    assert.match(html, new RegExp(`data-jcr-completion-filter="${filter}"`));
  assert.match(html, /checkin_missing[^>]*aria-pressed="true"/s);
});

test("missing GDB cards expose evidence, safe statuses and both operational actions", () => {
  const html = completionCard(completion.missing[0]);
  for (const text of ["Mario Rossi", "AB123CD", "Furgone", "Rientro", "18:00", "2h 15m", "Critico", "Apri Driver", "Apri GDB"])
    assert.match(html, new RegExp(text));
  assert.match(html, /data-jcr-missing-driver="DRV-077"/);
  assert.match(html, /data-jcr-missing-gdb=""/);
});

test("completion section explains its planning source and excluded exceptions", () => {
  const html = journalCompletionSection(completion, "all");
  assert.match(html, /Planning 42/);
  assert.match(html, /Driver con GDB mancanti/);
  assert.match(html, /1 eccezioni escluse/);
  assert.doesNotMatch(html, /location\.href|location\.reload|history\.pushState/);
});

test("Control Room and Fleet Vision consume backend completion without inventing data", async () => {
  const [control, aggregator, navigation, css] = await Promise.all([
    file("assets/js/modules/journal-control-room.js"),
    file("assets/js/modules/fleet-vision/aggregator.js"),
    file("assets/js/modules/fleet-vision/navigation.js"),
    file("assets/css/journal-completion.css"),
  ]);
  assert.match(control, /params\.completion_filter = state\.completion_filter/);
  assert.match(control, /journalCompletionSection\(\s*response\.completion/);
  assert.match(aggregator, /completion\?\.missing/);
  assert.match(aggregator, /completion\?\.decisions/);
  assert.match(navigation, /workspace:navigate/);
  assert.doesNotMatch(navigation, /location\.href|location\.reload/);
  for (const width of ["1100", "700", "600"])
    assert.match(css, new RegExp(`max-width:${width}px`));
  assert.match(css, /overflow-wrap:anywhere/);
});

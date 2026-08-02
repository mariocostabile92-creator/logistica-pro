import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { archiveCalendar } from "../assets/js/modules/journal-archive/calendar.js";
import { calendarDaySummary } from "../assets/js/modules/journal-archive/calendar-day-summary.js";
import { dailyTimeline } from "../assets/js/modules/journal-archive/daily-timeline.js";
import {
  liveCardPriority, liveKpiDefinitions, statusPresentation,
} from "../assets/js/modules/journal-control-room/live-status-presenter.js";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("calendar day communicates total anomalies incomplete media and accessible states", () => {
  const html = calendarDaySummary({
    date: "2026-08-02", day: 2, selectedDate: "2026-08-02", today: "2026-08-02",
    metrics: { total: 12, anomalies: 2, incomplete: 3, with_media: 8 },
  });
  for (const value of ["12", "GDB", "2 anomalie", "3 incomplete", "8 media",
    "has-anomalies", "has-incomplete", "active", "is-today", "aria-current=\"date\""]) {
    assert.match(html, new RegExp(value));
  }
  assert.match(html, /aria-label="2 agosto 2026: 12 GDB, 2 anomalie, 3 incomplete, 8 con allegati"/);
});

test("calendar renders a complete accessible grid including disabled outside days", () => {
  const html = archiveCalendar("2026-08", "2026-08-02", [], "2026-08-02");
  assert.equal((html.match(/class="gdb-calendar-day/g) || []).length, 42);
  assert.match(html, /disabled[\s\S]*Giorno fuori dal mese/);
  assert.match(html, /role="grid"/);
  assert.match(html, /Nessun GDB/i);
});

test("live status presenter keeps lifecycle anomaly and late priorities objective", () => {
  assert.equal(statusPresentation("generated").label, "Generata");
  assert.equal(statusPresentation("in_progress").label, "In compilazione");
  assert.equal(statusPresentation("completed").label, "Completata");
  assert.equal(statusPresentation("con_anomalia").label, "Completata con anomalia");
  assert.equal(liveCardPriority({ is_late: true, anomaly_present: true }).tone, "late");
  assert.equal(liveCardPriority({ is_late: false, anomaly_present: true }).tone, "anomaly");
  assert.deepEqual(liveKpiDefinitions.map(item => item[2]),
    ["all", "not_started", "in_progress", "completed", "anomaly", "late"]);
});

test("daily timeline preserves backend chronological order and exposes complete item facts", () => {
  const item = (id, time, operation) => ({
    id, occurred_at: `2026-08-02T${time}:00`, operational_date: "2026-08-02",
    declared_driver_identifier: `Driver ${id}`, plate_snapshot: `AA00${id}`,
    vehicle_model: "Van", operation_type: operation, status: "completed",
    anomaly_present: false, media: [], origin: "Shared link",
  });
  const html = dailyTimeline([
    item("A", "06:50", "check_out"), item("B", "18:15", "check_in"),
  ], "B");
  assert.ok(html.indexOf("Driver A") < html.indexOf("Driver B"));
  for (const value of ["06:50", "18:15", "Presa in carico", "Rientro", "Van",
    "Shared link", "0 allegati", "Apri GDB", "aria-pressed=\"true\""]) {
    assert.match(html, new RegExp(value));
  }
});

test("timeline mode remains SPA state and export has only a future action slot", async () => {
  const [state, archive, renderer, css] = await Promise.all([
    file("assets/js/modules/journal-archive/state.js"),
    file("assets/js/modules/journal-archive/index.js"),
    file("assets/js/modules/journal-archive/renderer.js"),
    file("assets/css/journal-calendar-intelligence.css"),
  ]);
  assert.match(state, /viewMode: "list"/);
  assert.match(state, /detailOpen: false/);
  assert.match(archive, /state\.viewMode = viewMode/);
  assert.match(archive, /state\.detailOpen = true/);
  assert.match(renderer, /data-gdb-day-action-slot/);
  assert.doesNotMatch(renderer + archive, />\s*(?:Esporta|PDF|ZIP)|data-gdb-export/i);
  assert.doesNotMatch(archive, /location\.href|location\.reload|history\.pushState/);
  assert.match(css, /@media\(max-width:1000px\)/);
  assert.match(css, /@media\(max-width:600px\)/);
});

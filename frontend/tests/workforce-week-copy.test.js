import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  renderWorkforceWeekCopyPreview,
  workforceWeekCopySummary,
  workforceWeekCopyValueLabel,
} from "../assets/js/modules/workforce-week-copy.js";


const page = readFileSync(new URL(
  "../assets/js/modules/workforce-page.js",
  import.meta.url,
), "utf8");
const api = readFileSync(new URL("../assets/js/api.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const css = readFileSync(new URL(
  "../assets/css/workforce-calendar.css",
  import.meta.url,
), "utf8");


function preview(overrides = {}) {
  const days = Array.from({ length: 7 }, (_, offset) => ({
    source_date: `2026-08-${String(10 + offset).padStart(2, "0")}`,
    target_date: `2026-08-${String(17 + offset).padStart(2, "0")}`,
    source: offset < 5
      ? { status_code: "scheduled", availability: true, shift_code: "C1" }
      : { status_code: "rest", availability: false, shift_code: null },
    target: null,
    will_overwrite: false,
  }));
  return {
    source_week_start: "2026-08-10",
    source_week_end: "2026-08-16",
    target_week_start: "2026-08-17",
    target_week_end: "2026-08-23",
    overwrite_count: 0,
    missing_count: 0,
    fingerprint: "f".repeat(64),
    days,
    ...overrides,
  };
}


test("week copy CTA is scoped to edit mode and hidden outside Week mode", () => {
  assert.match(html, /id="workforceWeekCopyOpen"[^>]*>Copia settimana precedente</);
  assert.match(page, /byId\("workforceWeekCopyOpen"\)\.hidden = viewMode !== "week"/);
  assert.match(page, /if \(!member \|\| viewMode !== "week"\) return/);
});


test("preview renders source and target periods with seven mapped rows", () => {
  const container = { innerHTML: "" };
  renderWorkforceWeekCopyPreview(container, preview());

  assert.equal((container.innerHTML.match(/workforce-week-copy-row/g) || []).length, 7);
  assert.match(container.innerHTML, /2026-08-10 → 2026-08-17/);
  assert.match(container.innerHTML, /Da copiare: <strong>C1<\/strong>/);
  assert.match(page, /source_week_start[\s\S]*source_week_end/);
  assert.match(page, /target_week_start[\s\S]*target_week_end/);
});


test("preview reports missing source without inventing rest", () => {
  const data = preview();
  data.days[2].source = null;
  data.missing_count = 1;
  const container = { innerHTML: "" };
  renderWorkforceWeekCopyPreview(container, data);

  assert.match(container.innerHTML, /Nessun turno da copiare/);
  assert.equal(workforceWeekCopySummary(data).copiedCount, 6);
  assert.equal(workforceWeekCopySummary(data).missingCount, 1);
});


test("existing target is visibly marked for explicit overwrite", () => {
  const data = preview();
  data.days[0].target = {
    status_code: "scheduled",
    availability: true,
    shift_code: "SA",
  };
  data.days[0].will_overwrite = true;
  data.overwrite_count = 1;
  const container = { innerHTML: "" };
  renderWorkforceWeekCopyPreview(container, data);

  assert.match(container.innerHTML, /Esistente: <strong>SA<\/strong>/);
  assert.match(container.innerHTML, /Verrà sostituito/);
  assert.equal(workforceWeekCopySummary(data).overwriteCount, 1);
});


test("preview labels preserve supported shifts, statuses and times", () => {
  assert.equal(workforceWeekCopyValueLabel(null), "Nessun turno da copiare");
  assert.equal(workforceWeekCopyValueLabel({ status_code: "rest" }), "Riposo");
  assert.equal(workforceWeekCopyValueLabel({
    status_code: "scheduled",
    shift_code: "C1",
    start_time: "08:30",
    end_time: "17:30",
  }), "C1 · 08:30–17:30");
});


test("cancel closes preview and performs no write", () => {
  assert.match(page, /workforceWeekCopyCancel"\)\.addEventListener\("click", closeWeekCopyPreview\)/);
  assert.doesNotMatch(page, /function closeWeekCopyPreview[\s\S]{0,400}applyWorkforceWeekCopy/);
});


test("confirm uses authoritative fingerprint and handles stale preview with refresh", () => {
  assert.match(api, /week-copy\/preview/);
  assert.match(api, /week-copy`, \{[\s\S]*method: "POST"/);
  assert.match(page, /expected_fingerprint: weekCopyPreview\.fingerprint/);
  assert.match(page, /WORKFORCE_WEEK_COPY_STALE/);
  assert.match(page, /weekCopyPreview = await previewWorkforceWeekCopy\(memberId, targetWeekStart\)/);
  assert.match(page, /I turni sono cambiati dall'anteprima/);
});


test("successful copy refreshes target week and restores clean same-driver edit mode", () => {
  assert.match(page, /await loadCalendar\(\{[\s\S]*dateFrom: targetWeekStart[\s\S]*dateTo: addDays\(targetWeekStart, 6\)/);
  assert.match(page, /Number\(item\.workforce_member_id\) === memberId/);
  assert.match(page, /startMultiDayEditing\(member, trigger\)/);
  assert.match(page, /showWorkforceFeedback\("Settimana copiata\."\)/);
});


test("mobile dialog stays inside 390px and actions keep touch targets", () => {
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*\.workforce-week-copy-dialog \{[\s\S]*width: calc\(100vw - 16px\)/);
  assert.match(css, /\.workforce-week-copy-row \{[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /\.workforce-week-copy-dialog > footer button \{[\s\S]*min-height: 44px/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyIdentitySourceEvent,
  createIdentitySourceState,
  mapWithConcurrency,
} from "../assets/js/modules/dsp-quality/identity-source.js";
import {
  identitySourceMarkup,
  isSafeInlineSuggestion,
} from "../assets/js/modules/dsp-quality/identity-source-presenter.js";
import { qualityDriversMarkup } from "../assets/js/modules/dsp-quality/drivers-presenter.js";
import { reconciliationMarkup } from "../assets/js/modules/dsp-quality/reconciliation-presenter.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function fixture(suggestionCount = 128, unresolvedCount = 25) {
  const suggested = Array.from({ length: suggestionCount }, (_, index) => ({
    transporter_external_id: index === 0 ? "A1220Y3BKP176Z" : `TID-${index + 1}`,
    source_driver_value: index === 0 ? "Yassine Zyadi" : `Driver ${index + 1}`,
    proposed_workforce_member_id: index + 1,
    proposed_display_name: index === 0 ? "Yassine Zyadi" : `Driver ${index + 1}`,
    status: "SUGGESTED",
    reason: "Corrispondenza da confermare.",
  }));
  const unresolved = Array.from({ length: unresolvedCount }, (_, index) => ({
    transporter_external_id: `UNRESOLVED-${index + 1}`,
    source_driver_value: "Non disponibile",
    status: "UNRESOLVED",
    reason: "Non trovato",
  }));
  const preview = {
    valid: true,
    source: { filename: "Planning.xlsx", sheet: "Planning", rows_detected: 142 },
    coverage: {
      quality_transporters: suggestionCount + unresolvedCount,
      already_verified: 0,
      exact_matches: 0,
      suggestions: suggestionCount,
      unresolved: unresolvedCount,
      conflicts: 0,
    },
    rows: [...suggested, ...unresolved],
  };
  const reconciliationRows = suggested.map(row => ({
    transporter_external_id: row.transporter_external_id,
    mapping_status: "UNMAPPED",
    workforce_member_id: null,
    workforce_display_name: null,
    updated_at: null,
  }));
  return { suggested, unresolved, preview, reconciliationRows };
}


function sourceState(data, overrides = {}) {
  return {
    ...createIdentitySourceState(),
    phase: "available",
    bucket: "suggested",
    preview: data.preview,
    reconciliationRows: data.reconciliationRows,
    ...overrides,
  };
}


test("128 suggested rows render direct confirmation choose-other and checkbox actions", () => {
  const html = identitySourceMarkup(sourceState(fixture()));
  assert.match(html, /Yassine Zyadi/);
  assert.equal((html.match(/data-quality-suggestion-confirm=/g) || []).length, 128);
  assert.equal((html.match(/data-quality-suggestion-choose=/g) || []).length, 128);
  assert.equal((html.match(/data-quality-suggestion-select=/g) || []).length, 128);
  assert.doesNotMatch(html, /Rivedi suggerimenti/);
});


test("only safe suggestions can be selected and confirmed", () => {
  const row = fixture(1, 0).suggested[0];
  assert.equal(isSafeInlineSuggestion(row, {
    mapping_status: "UNMAPPED",
    workforce_member_id: null,
  }), true);
  assert.equal(isSafeInlineSuggestion(row, {
    mapping_status: "MATCHED",
    workforce_member_id: 99,
  }), false);
  assert.equal(isSafeInlineSuggestion({ ...row, status: "CONFLICT" }, {
    mapping_status: "UNMAPPED",
  }), false);
  assert.equal(isSafeInlineSuggestion({ ...row, proposed_workforce_member_id: null }, {
    mapping_status: "UNMAPPED",
  }), false);
});


test("single confirmation immediately renders ASSOCIATO and updates summaries", () => {
  const data = fixture(1, 0);
  const externalId = data.suggested[0].transporter_external_id;
  let state = sourceState(data);
  state = applyIdentitySourceEvent(state, {
    type: "identity-source-suggestion-confirmed",
    externalId,
  });
  const html = identitySourceMarkup({
    ...state,
    reconciliationRows: [{
      ...data.reconciliationRows[0],
      mapping_status: "MATCHED",
      workforce_member_id: 1,
      workforce_display_name: "Yassine Zyadi",
    }],
  });
  assert.match(html, /data-source-status="ASSOCIATO"/);
  assert.match(html, /Workforce[\s\S]*Yassine Zyadi/);
  assert.match(html, /Già associati[\s\S]*>1</);
  assert.match(html, /Da verificare[\s\S]*>0</);

  const reconciliation = reconciliationMarkup({
    open: true,
    phase: "available",
    data: { summary: { total: 153, matched: 1, unmapped: 152, ambiguous: 0 }, rows: [] },
    filter: "all",
    search: "",
    sourceUnresolvedIds: [],
    identitySource: createIdentitySourceState(),
  });
  assert.match(reconciliation, /Associati[\s\S]*1/);
  assert.match(reconciliation, /Da associare[\s\S]*152/);
});


test("five selected suggestions require an explicit bulk confirmation dialog", () => {
  const data = fixture(5, 0);
  let state = sourceState(data);
  state = applyIdentitySourceEvent(state, {
    type: "identity-source-suggestion-visible-selection-changed",
    selected: true,
    externalIds: data.suggested.map(row => row.transporter_external_id),
  });
  assert.match(identitySourceMarkup(state), /Conferma selezionati \(5\)/);
  assert.doesNotMatch(identitySourceMarkup(state), /role="dialog"/);
  state = applyIdentitySourceEvent(state, { type: "identity-source-bulk-dialog-opened" });
  const dialog = identitySourceMarkup(state);
  assert.match(dialog, /role="dialog"/);
  assert.match(dialog, /Stai per associare 5 Transporter/);
  assert.match(dialog, /Conferma 5 associazioni/);
});


test("bulk completion preserves partial failures for a new review", () => {
  const data = fixture(5, 0);
  const ids = data.suggested.map(row => row.transporter_external_id);
  let state = sourceState(data, { selectedSuggestionIds: ids });
  state = applyIdentitySourceEvent(state, {
    type: "identity-source-bulk-completed",
    confirmedIds: ids.slice(0, 3),
    failedIds: ids.slice(3),
  });
  assert.deepEqual(state.selectedSuggestionIds, ids.slice(3));
  assert.deepEqual(state.failedSuggestionIds, ids.slice(3));
  assert.deepEqual(state.bulkResult, { confirmed: 3, failed: 2 });
  assert.match(identitySourceMarkup(state), /3 associazioni confermate\. 2 da rivedere/);
});


test("bulk worker never exceeds concurrency four", async () => {
  let active = 0;
  let maximum = 0;
  const results = await mapWithConcurrency(Array.from({ length: 12 }, (_, index) => index), 4, async item => {
    active += 1;
    maximum = Math.max(maximum, active);
    await new Promise(resolve => setTimeout(resolve, 2));
    active -= 1;
    return item;
  });
  assert.equal(results.length, 12);
  assert.equal(maximum, 4);
});


test("controller uses the existing PUT for single and bulk without automatic mapping", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const single = controller.slice(
    controller.indexOf("async function confirmInlineSuggestion"),
    controller.indexOf("function chooseInlineSuggestionCandidate"),
  );
  const bulk = controller.slice(
    controller.indexOf("async function confirmInlineBulkSuggestions"),
    controller.indexOf("function handoffUnresolvedSuggestions"),
  );
  assert.match(single, /putTransporterMapping/);
  assert.match(single, /expected_updated_at/);
  assert.match(bulk, /mapWithConcurrency\(selected, 4/);
  assert.match(bulk, /putTransporterMapping/);
  assert.doesNotMatch(controller, /bulk-mapping|autoMapping|autoConfirm/);
});


test("matched Driver row shows Workforce name first, Transporter ID second and preserves metrics", () => {
  const metric = (key, raw) => ({ metric_key: key, current: { value_state: "PRESENT", raw_value: raw } });
  const html = qualityDriversMarkup({
    phase: "available",
    canManageMappings: true,
    filter: "all",
    search: "",
    sort: { key: "row_index", direction: "asc" },
    data: {
      available: true,
      drivers_available: true,
      current_period: { week: 46, year: 2026 },
      summary: { total: 1, matched: 1, unmapped: 0 },
      rows: [{
        row_id: "row-1",
        row_index: 1,
        transporter_external_id: "A1220Y3BKP176Z",
        mapping_status: "MATCHED",
        workforce_member_id: 1,
        workforce_display_name: "Yassine Zyadi",
        metrics: [
          metric("delivery_completion_rate", "98.04%"),
          metric("photo_on_delivery", "100%"),
          metric("contact_compliance", "100%"),
          metric("delivery_success_conditions_dpmo", "0"),
          metric("customer_delivery_feedback_dpmo", "6667"),
          metric("customer_escalations_count", "0"),
          metric("delivered", "150"),
        ],
      }],
    },
    reconciliation: { open: false },
  });
  assert.match(html, /<strong>Yassine Zyadi<\/strong>[\s\S]*<span>A1220Y3BKP176Z<\/span>/);
  assert.doesNotMatch(html, /<strong>Transporter A1220Y3BKP176Z<\/strong>/);
  for (const value of ["98.04%", "100%", "6667", "150"]) assert.match(html, new RegExp(value.replace("%", "%")));
});


test("unresolved rows remain unchanged and have no suggestion confirmation", () => {
  const data = fixture(1, 25);
  const html = identitySourceMarkup(sourceState(data, { bucket: "unresolved" }));
  assert.equal((html.match(/data-source-status="UNRESOLVED"/g) || []).length, 25);
  assert.doesNotMatch(html, /data-quality-suggestion-confirm=/);
});

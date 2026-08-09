import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { identitySourceMarkup } from "../assets/js/modules/dsp-quality/identity-source-presenter.js";
import { filterReconciliationRows } from "../assets/js/modules/dsp-quality/reconciliation-presenter.js";
import {
  applyReconciliationEvent,
  createReconciliationState,
} from "../assets/js/modules/dsp-quality/reconciliation-state.js";
import {
  applySuggestionReviewEvent,
  createSuggestionReviewState,
  currentSuggestion,
  isReviewShortcutTarget,
  suggestionQueue,
  suggestionReviewProgress,
} from "../assets/js/modules/dsp-quality/suggestion-review.js";
import { suggestionReviewMarkup } from "../assets/js/modules/dsp-quality/suggestion-review-presenter.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const suggestions = Array.from({ length: 4 }, (_, index) => ({
  transporter_external_id: `TID-${index + 1}`,
  source_driver_value: ["Alban Beqiraj", "Alessandro Facchetti", "Angelo De Simone", "Mario Rossi"][index],
  proposed_workforce_member_id: index + 10,
  proposed_display_name: ["Alban Beqiraj", "Alessandro Facchetti", "Angelo De Simone", "Mario Rossi"][index],
  evidence_source: "GENERIC_FILE_EXACT",
  status: "SUGGESTED",
  reason: "Nome esatto e univoco: richiede conferma manuale.",
}));
const preview = {
  valid: true,
  scorecard_id: "week-45",
  preview_token: "signed-token",
  default_bucket: "suggested",
  source: { filename: "Planning.xlsx", sheet: "Planning", transporter_column: "T-ID", driver_column: "drivers", rows_detected: 6 },
  coverage: { quality_transporters: 8, suggestions: 4, unresolved: 1, conflicts: 1, exact_matches: 1, already_verified: 1 },
  rows: [
    ...suggestions,
    { transporter_external_id: "EXACT", status: "EXACT" },
    { transporter_external_id: "MISSING", status: "UNRESOLVED" },
    { transporter_external_id: "CONFLICT", status: "CONFLICT" },
    { transporter_external_id: "VERIFIED", status: "ALREADY_VERIFIED" },
  ],
};


function opened(sourcePreview = preview, scorecardId = "week-45") {
  return applySuggestionReviewEvent(createSuggestionReviewState(), {
    type: "suggestion-review-opened",
    preview: sourcePreview,
    scorecardId,
  });
}


function sourceState(review = createSuggestionReviewState()) {
  return {
    phase: "available",
    preview,
    bucket: "suggested",
    review,
    selection: {},
    reconciliationRows: suggestions.map(row => ({
      transporter_external_id: row.transporter_external_id,
      mapping_status: "UNMAPPED",
      workforce_member_id: null,
      updated_at: null,
    })),
  };
}


test("inline confirmation is visible when suggestions exist", () => {
  const html = identitySourceMarkup(sourceState());
  assert.match(html, /data-quality-suggestion-confirm="TID-1"/);
  assert.match(html, /Scegli altro/);
  assert.doesNotMatch(html, /Rivedi suggerimenti/);
});


test("inline toolbar shows the dynamic selected count", () => {
  assert.match(identitySourceMarkup(sourceState()), /Conferma selezionati \(0\)/);
});


test("opening review creates a dedicated session", () => {
  const state = opened();
  assert.equal(state.open, true);
  assert.equal(state.scorecardId, "week-45");
});


test("review starts at 1 of N", () => {
  assert.match(suggestionReviewMarkup(opened(), preview), /1 di 4/);
});


test("current review renders Transporter ID", () => {
  assert.match(suggestionReviewMarkup(opened(), preview), /TID-1/);
});


test("current review renders source driver", () => {
  assert.match(suggestionReviewMarkup(opened(), preview), /Fonte driver[\s\S]*Alban Beqiraj/);
});


test("current review renders suggested Workforce", () => {
  assert.match(suggestionReviewMarkup(opened(), preview), /Workforce suggerito[\s\S]*Alban Beqiraj/);
});


test("current review renders evidence confidence and human status", () => {
  const html = suggestionReviewMarkup(opened(), preview);
  assert.match(html, /Fonte evidenza/);
  assert.match(html, /Confidence/);
  assert.match(html, /SUGGESTED/);
  assert.match(html, /Da verificare/);
});


test("review exposes explicit confirm action", () => {
  assert.match(suggestionReviewMarkup(opened(), preview), /data-quality-review-confirm[\s\S]*Conferma/);
});


test("controller confirms through the existing Q8 PUT", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /confirmSuggestionReview[\s\S]*putTransporterMapping/);
});


test("confirmation advances to the next suggestion", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-confirmed" });
  assert.equal(currentSuggestion(state).transporter_external_id, "TID-2");
});


test("skip records no mapping and advances", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-skipped" });
  assert.deepEqual(state.skipped, ["TID-1"]);
  assert.deepEqual(state.confirmed, []);
  assert.equal(currentSuggestion(state).transporter_external_id, "TID-2");
});


test("choose other opens the Workforce selector", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-choose-opened", search: "Alban Beqiraj" });
  assert.equal(state.chooserOpen, true);
  assert.match(suggestionReviewMarkup(state, preview), /Cerca in Workforce/);
});


test("candidate search reuses the Q8 Workforce endpoint", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /loadReviewCandidates[\s\S]*searchQualityWorkforceCandidates/);
});


test("candidate click selects but never confirms", () => {
  const candidate = { workforce_member_id: 77, display_name: "Altro Driver" };
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-candidate-selected", candidate });
  assert.equal(state.currentSelection, candidate);
  assert.deepEqual(state.confirmed, []);
});


test("chosen candidate still requires explicit confirmation", () => {
  let state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-choose-opened", search: "Altro" });
  state = applySuggestionReviewEvent(state, { type: "suggestion-review-candidate-selected", candidate: { workforce_member_id: 77, display_name: "Altro Driver" } });
  assert.match(suggestionReviewMarkup(state, preview), /Conferma questo driver/);
});


test("confirmed progress is counted", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-confirmed" });
  assert.equal(suggestionReviewProgress(state).confirmed, 1);
});


test("skipped progress is counted without an error", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-skipped" });
  assert.equal(suggestionReviewProgress(state).skipped, 1);
  assert.equal(state.error, null);
});


test("409 conflict keeps the current suggestion", () => {
  const state = applySuggestionReviewEvent(opened(), { type: "suggestion-review-conflict", message: "L’associazione è cambiata. Ricarica il suggerimento." });
  assert.equal(state.currentIndex, 0);
  assert.match(suggestionReviewMarkup(state, preview), /L’associazione è cambiata/);
});


test("queue contains only SUGGESTED evidence", () => {
  assert.deepEqual(suggestionQueue(preview).map(row => row.transporter_external_id), suggestions.map(row => row.transporter_external_id));
});


test("queue excludes verified mappings", () => {
  assert.ok(!suggestionQueue(preview).some(row => row.status === "ALREADY_VERIFIED"));
});


test("queue excludes unresolved evidence", () => {
  assert.ok(!suggestionQueue(preview).some(row => row.status === "UNRESOLVED"));
});


test("queue excludes conflicts", () => {
  assert.ok(!suggestionQueue(preview).some(row => row.status === "CONFLICT"));
});


test("opening another selected scorecard resets the queue", () => {
  const progressed = applySuggestionReviewEvent(opened(), { type: "suggestion-review-confirmed" });
  const otherPreview = { ...preview, rows: [{ ...suggestions[0], transporter_external_id: "OTHER" }] };
  const changed = applySuggestionReviewEvent(progressed, { type: "suggestion-review-opened", preview: otherPreview, scorecardId: "week-46" });
  assert.equal(changed.scorecardId, "week-46");
  assert.equal(changed.currentIndex, 0);
  assert.equal(currentSuggestion(changed).transporter_external_id, "OTHER");
});


test("close and reopen resumes the same session", () => {
  const progressed = applySuggestionReviewEvent(opened(), { type: "suggestion-review-skipped" });
  const closed = applySuggestionReviewEvent(progressed, { type: "suggestion-review-closed" });
  const resumed = applySuggestionReviewEvent(closed, { type: "suggestion-review-opened", preview, scorecardId: "week-45" });
  assert.equal(resumed.currentIndex, 1);
  assert.equal(currentSuggestion(resumed).transporter_external_id, "TID-2");
});


test("manual review confirmation is independent from preview token expiry", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const block = controller.slice(controller.indexOf("async function confirmSuggestionReview"), controller.indexOf("function handoffUnresolvedSuggestions"));
  assert.match(block, /putTransporterMapping/);
  assert.doesNotMatch(block, /preview_token|applyExactTransporterIdentitySource/);
});


test("completion state is explicit", () => {
  let state = opened();
  for (let index = 0; index < 4; index += 1) state = applySuggestionReviewEvent(state, { type: "suggestion-review-confirmed" });
  assert.equal(suggestionReviewProgress(state).complete, true);
  assert.match(suggestionReviewMarkup(state, preview), /Revisione completata/);
});


test("completion offers unresolved manual handoff", () => {
  let state = opened();
  for (let index = 0; index < 4; index += 1) state = applySuggestionReviewEvent(state, { type: "suggestion-review-skipped" });
  assert.match(suggestionReviewMarkup(state, preview), /Gestisci i non trovati/);
});


test("unresolved handoff activates the existing manual reconciliation list", () => {
  const state = applyReconciliationEvent(createReconciliationState(), {
    type: "suggestion-review-unresolved-handoff",
    externalIds: ["MISSING"],
  });
  const rows = [
    { transporter_external_id: "MISSING", mapping_status: "UNMAPPED" },
    { transporter_external_id: "OTHER", mapping_status: "UNMAPPED" },
  ];
  assert.equal(state.filter, "source-unresolved");
  assert.deepEqual(filterReconciliationRows(rows, state.filter, "", state.sourceUnresolvedIds), [rows[0]]);
});


test("keyboard Enter confirms and S skips", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /event\.key === "Enter"[\s\S]*confirmSuggestionReview/);
  assert.match(controller, /toLocaleLowerCase\("it"\) === "s"[\s\S]*skipSuggestionReview/);
});


test("opening review focuses confirmation before the close fallback", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const confirmPosition = controller.indexOf('root.querySelector("[data-quality-review-confirm]")');
  const closePosition = controller.indexOf('root.querySelector("[data-quality-review-close]")');
  assert.ok(confirmPosition >= 0);
  assert.ok(closePosition > confirmPosition);
});


test("Escape closes chooser before the review", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /event\.key === "Escape"[\s\S]*review\.chooserOpen[\s\S]*suggestion-review-choose-closed/);
});


test("shortcuts never intercept text inputs", () => {
  assert.equal(isReviewShortcutTarget({ matches: selector => selector.includes("input") }), true);
});


test("review shortcuts remain active while an action button has focus", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.doesNotMatch(controller, /isReviewShortcutTarget\(event\.target\) \|\| event\.target\.matches\("button, a"\)/);
});


test("async Workforce results restore focus to the review chooser", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /suggestion-review-candidates-completed[\s\S]*focusSuggestionReview\(\)/);
});


test("390 layout is vertical with touch targets and no fixed viewport width", async () => {
  const css = await source("assets/css/dsp-quality.css");
  assert.match(css, /@media \(max-width: 620px\)[\s\S]*dsp-quality-suggestion-review[\s\S]*width: 100%/);
  assert.match(css, /dsp-quality-suggestion-review button[\s\S]*min-height: 44px/);
  assert.doesNotMatch(css, /width:\s*(?:390|768|1440)px/);
});


test("manual Q8 fallback remains unchanged", () => {
  assert.match(identitySourceMarkup(sourceState()), /Associa manualmente/);
});


test("Q8.2 source metadata and buckets remain visible", () => {
  const html = identitySourceMarkup(sourceState());
  assert.match(html, /Planning\.xlsx/);
  assert.match(html, /T-ID/);
  assert.match(html, /Da verificare \(4\)/);
});


test("confirmation refreshes Q7 and Q8 without reload", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const block = controller.slice(controller.indexOf("async function confirmSuggestionReview"), controller.indexOf("function handoffUnresolvedSuggestions"));
  assert.match(block, /loadDrivers\(\{ force: true \}\)/);
  assert.match(block, /loadReconciliation\(\{ keepFilter: true, silent: true \}\)/);
  assert.doesNotMatch(block, /location\.|reload\(/);
});


test("suggested bucket renders inline controls on every reviewable row", () => {
  const html = identitySourceMarkup(sourceState());
  assert.equal((html.match(/data-source-status="SUGGESTED"/g) || []).length, 4);
  assert.equal((html.match(/data-quality-suggestion-confirm=/g) || []).length, 4);
  assert.equal((html.match(/data-quality-suggestion-select=/g) || []).length, 4);
});

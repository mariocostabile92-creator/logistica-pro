import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { identityRowsForBucket } from "../assets/js/modules/dsp-quality/identity-source.js";
import { identitySourceMarkup } from "../assets/js/modules/dsp-quality/identity-source-presenter.js";
import {
  applySuggestionReviewEvent,
  createSuggestionReviewState,
} from "../assets/js/modules/dsp-quality/suggestion-review.js";
import { suggestionReviewMarkup } from "../assets/js/modules/dsp-quality/suggestion-review-presenter.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function productionPreview() {
  const suggested = Array.from({ length: 128 }, (_, index) => ({
    transporter_external_id: `SUGGESTED-${index + 1}`,
    source_driver_value: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    proposed_workforce_member_id: index + 1,
    proposed_display_name: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    evidence_source: "NAME_SUGGESTION",
    confidence: "SUGGESTED",
    status: "SUGGESTED",
    reason: "Nome esatto e univoco: richiede conferma manuale.",
  }));
  const unresolved = Array.from({ length: 25 }, (_, index) => ({
    transporter_external_id: `UNRESOLVED-${index + 1}`,
    source_driver_value: `Non trovato ${index + 1}`,
    status: "UNRESOLVED",
    reason: "Nessun membro Workforce corrisponde alla fonte.",
  }));
  return {
    valid: true,
    scorecard_id: "week-46",
    preview_token: "existing-preview-token",
    default_bucket: "suggested",
    source: {
      filename: "Planning.xlsx",
      sheet: "Planning",
      transporter_column: "T-ID",
      driver_column: "drivers",
      rows_detected: 142,
    },
    coverage: {
      quality_transporters: 153,
      suggestions: 128,
      unresolved: 25,
      conflicts: 0,
      exact_matches: 0,
      already_verified: 0,
    },
    rows: [...suggested, ...unresolved],
  };
}


function identityState(preview, bucket = "suggested", review = createSuggestionReviewState()) {
  return { phase: "available", preview, bucket, review, selection: {} };
}


test("production fixture exposes 128 suggested and 25 unresolved rows", () => {
  const preview = productionPreview();
  assert.equal(identityRowsForBucket(preview.rows, "suggested").length, 128);
  assert.equal(identityRowsForBucket(preview.rows, "unresolved").length, 25);
});


test("Da verificare renders the existing 128 suggestions and review entry", () => {
  const html = identitySourceMarkup(identityState(productionPreview()));
  assert.equal((html.match(/data-source-status="SUGGESTED"/g) || []).length, 128);
  assert.match(html, /data-quality-suggestion-review-open/);
});


test("Non trovate keeps rendering the existing 25 unresolved rows", () => {
  const html = identitySourceMarkup(identityState(productionPreview(), "unresolved"));
  assert.equal((html.match(/data-source-status="UNRESOLVED"/g) || []).length, 25);
});


test("review opens from the current preview at 1 of 128", () => {
  const preview = productionPreview();
  const review = applySuggestionReviewEvent(createSuggestionReviewState(), {
    type: "suggestion-review-opened",
    preview,
    scorecardId: "week-46",
  });
  assert.equal(review.queue.length, 128);
  assert.match(suggestionReviewMarkup(review, preview), /1 di 128/);
  assert.match(suggestionReviewMarkup(review, preview), /SUGGESTED-1/);
});


test("review click is terminal and never regenerates source preview", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const openBlock = controller.slice(
    controller.indexOf("function openSuggestionReview"),
    controller.indexOf("function closeSuggestionReview"),
  );
  assert.match(openBlock, /source\.preview/);
  assert.doesNotMatch(openBlock, /analyzeIdentitySource|previewTransporterIdentitySource|source-preview/);
  assert.match(controller, /data-quality-suggestion-review-open[\s\S]*openSuggestionReview\(\);[\s\S]*return;/);
});


test("rapid manual search cancels obsolete work and ignores stale responses", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const inputBlock = controller.slice(
    controller.indexOf('if (event.target.matches("[data-quality-candidate-search]"))'),
    controller.indexOf('if (event.target.matches("[data-quality-review-search]"))'),
  );
  const loaderBlock = controller.slice(
    controller.indexOf("async function loadCandidates"),
    controller.indexOf("function mappingErrorMessage"),
  );
  assert.match(inputBlock, /candidateRequestController\?\.abort\(\)/);
  assert.match(inputBlock, /candidateRequestVersion \+= 1/);
  assert.match(inputBlock, /setTimeout\(\(\) => void loadCandidates\(query, version\), 225\)/);
  assert.match(loaderBlock, /version !== candidateRequestVersion/);
  assert.match(loaderBlock, /candidateSearch === query/);
  assert.match(loaderBlock, /commitCandidateRegion/);
});


test("manual confirmation remains the existing Q8 PUT without auto-confirm", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const confirmation = controller.slice(
    controller.indexOf("async function confirmSuggestionReview"),
    controller.indexOf("function handoffUnresolvedSuggestions"),
  );
  assert.match(confirmation, /putTransporterMapping/);
  assert.doesNotMatch(confirmation, /applyExactTransporterIdentitySource|previewTransporterIdentitySource/);
});

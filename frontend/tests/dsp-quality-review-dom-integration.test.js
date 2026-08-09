import assert from "node:assert/strict";
import test from "node:test";

import { identitySourceMarkup } from "../assets/js/modules/dsp-quality/identity-source-presenter.js";
import {
  applySuggestionReviewEvent,
  createSuggestionReviewState,
} from "../assets/js/modules/dsp-quality/suggestion-review.js";
import {
  mountSuggestionReview,
} from "../assets/js/modules/dsp-quality/suggestion-review-presenter.js";


function previewFixture() {
  const suggested = Array.from({ length: 128 }, (_, index) => ({
    transporter_external_id: `TID-${String(index + 1).padStart(3, "0")}`,
    source_driver_value: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    proposed_workforce_member_id: index + 1,
    proposed_display_name: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    status: "SUGGESTED",
  }));
  const unresolved = Array.from({ length: 25 }, (_, index) => ({
    transporter_external_id: `MISSING-${index + 1}`,
    source_driver_value: `Non trovato ${index + 1}`,
    status: "UNRESOLVED",
  }));
  return {
    valid: true,
    source: { filename: "Planning.xlsx", sheet: "Planning", rows_detected: 142 },
    coverage: { suggestions: 128, unresolved: 25 },
    rows: [...suggested, ...unresolved],
  };
}


test("review is mounted into the dedicated DOM host and advances after one confirmation", () => {
  const preview = previewFixture();
  const sourceState = {
    phase: "available",
    preview,
    bucket: "suggested",
    review: createSuggestionReviewState(),
  };
  const workspaceHtml = identitySourceMarkup(sourceState);
  assert.match(workspaceHtml, /data-quality-suggestion-review-open/);
  assert.match(workspaceHtml, /data-quality-suggestion-review-host/);

  const host = { innerHTML: "", hidden: true };
  const root = {
    querySelector(selector) {
      return selector === "[data-quality-suggestion-review-host]" ? host : null;
    },
  };
  let review = applySuggestionReviewEvent(sourceState.review, {
    type: "suggestion-review-opened",
    preview,
    scorecardId: "week-46",
  });
  assert.equal(mountSuggestionReview(root, review, preview), true);
  assert.equal(host.hidden, false);
  assert.match(host.innerHTML, /Revisione associazioni/);
  assert.match(host.innerHTML, /1 di 128/);
  assert.match(host.innerHTML, /data-quality-review-confirm/);
  assert.match(host.innerHTML, /data-quality-review-choose/);
  assert.match(host.innerHTML, /data-quality-review-skip/);

  review = applySuggestionReviewEvent(review, { type: "suggestion-review-confirmed" });
  mountSuggestionReview(root, review, preview);
  assert.match(host.innerHTML, /2 di 128/);
});

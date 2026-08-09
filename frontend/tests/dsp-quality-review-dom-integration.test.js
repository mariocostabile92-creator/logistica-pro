import assert from "node:assert/strict";
import test from "node:test";

import { identitySourceMarkup } from "../assets/js/modules/dsp-quality/identity-source-presenter.js";


test("legacy review is no longer required by the primary suggestion workflow", () => {
  const rows = Array.from({ length: 128 }, (_, index) => ({
    transporter_external_id: `TID-${index + 1}`,
    source_driver_value: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    proposed_workforce_member_id: index + 1,
    proposed_display_name: index === 0 ? "Alban Beqiraj" : `Driver ${index + 1}`,
    status: "SUGGESTED",
  }));
  const html = identitySourceMarkup({
    phase: "available",
    bucket: "suggested",
    preview: {
      valid: true,
      source: { filename: "Planning.xlsx", rows_detected: 142 },
      coverage: { suggestions: 128, unresolved: 25 },
      rows,
    },
    reconciliationRows: rows.map(row => ({
      transporter_external_id: row.transporter_external_id,
      mapping_status: "UNMAPPED",
      workforce_member_id: null,
    })),
    selectedSuggestionIds: [],
  });
  assert.match(html, /data-quality-suggestion-review-host hidden/);
  assert.doesNotMatch(html, /data-quality-suggestion-review-open/);
  assert.equal((html.match(/data-quality-suggestion-confirm=/g) || []).length, 128);
  assert.equal((html.match(/data-quality-suggestion-choose=/g) || []).length, 128);
  assert.equal((html.match(/data-quality-suggestion-select=/g) || []).length, 128);
});

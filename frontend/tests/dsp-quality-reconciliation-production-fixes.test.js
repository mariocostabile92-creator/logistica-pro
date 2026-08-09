import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  previewTransporterIdentitySource,
} from "../assets/js/modules/dsp-quality/api.js";
import {
  reconciliationCandidateRegionMarkup,
  updateReconciliationCandidateRegion,
} from "../assets/js/modules/dsp-quality/reconciliation-presenter.js";
import {
  applyReconciliationEvent,
  createReconciliationState,
} from "../assets/js/modules/dsp-quality/reconciliation-state.js";


const source = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


function activeState(overrides = {}) {
  return {
    ...createReconciliationState(),
    open: true,
    phase: "available",
    activeExternalId: "A3638D6C2AN2C3",
    data: {
      rows: [{
        transporter_external_id: "A3638D6C2AN2C3",
        mapping_status: "UNMAPPED",
      }],
    },
    ...overrides,
  };
}


test("Workforce search accepts A, Al, Alb and Alban as one state sequence", () => {
  let state = activeState();
  for (const search of ["A", "Al", "Alb", "Alban"]) {
    state = applyReconciliationEvent(state, {
      type: "candidate-search-changed",
      search,
    });
  }
  assert.equal(state.candidateSearch, "Alban");
  assert.equal(state.candidatePhase, "loading");
});


test("candidate result refresh does not replace or mutate the search input", () => {
  const input = { value: "Alban Beqiraj", selectionStart: 14, focused: true };
  const region = { innerHTML: "old" };
  const root = {
    querySelector(selector) {
      if (selector === "[data-quality-candidate-region]") return region;
      if (selector === "[data-quality-candidate-search]") return input;
      return null;
    },
  };
  const state = activeState({
    candidateSearch: input.value,
    candidatePhase: "available",
    candidates: [{
      workforce_member_id: 42,
      display_name: "Alban Beqiraj",
      external_identifier: "WF-ALBAN",
      station: "DLO2",
      contract: "Full time",
      active: true,
    }],
  });

  assert.equal(updateReconciliationCandidateRegion(root, state), true);
  assert.equal(input.value, "Alban Beqiraj");
  assert.equal(input.selectionStart, 14);
  assert.equal(input.focused, true);
  assert.match(region.innerHTML, /Alban Beqiraj/);
});


test("localized result region renders loading, empty and candidates", () => {
  assert.match(reconciliationCandidateRegionMarkup(activeState({ candidatePhase: "loading" })), /Ricerca driver/);
  assert.match(reconciliationCandidateRegionMarkup(activeState({ candidatePhase: "available", candidates: [] })), /Nessun driver Workforce trovato/);
  assert.match(reconciliationCandidateRegionMarkup(activeState({
    candidatePhase: "available",
    candidates: [{ workforce_member_id: 7, display_name: "Alban Beqiraj", active: true }],
  })), /data-quality-candidate-id="7"/);
});


test("input handler keeps debounce and avoids destructive full commit or refocus", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  const branch = controller.match(/if \(event\.target\.matches\("\[data-quality-candidate-search\]"\)\) \{([\s\S]*?)\n    \}/)?.[1] || "";
  assert.match(branch, /commitCandidateRegion/);
  assert.match(branch, /setTimeout\(\(\) => void loadCandidates\(query\), 250\)/);
  assert.doesNotMatch(branch, /\bcommit\(|requestAnimationFrame|\.focus\(/);
});


test("Planning source preview keeps frontend and backend route contract", async () => {
  let request;
  await previewTransporterIdentitySource({
    scorecardId: "week-46-2025",
    usePlanning: true,
  }, {
    fetcher: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ valid: true, rows: [] }) };
    },
  });
  assert.equal(request.url, "/api/dsp-quality/transporter-mappings/source-preview");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.body.get("use_planning"), "true");
  assert.equal(request.options.body.get("scorecard_id"), "week-46-2025");
});


test("manual association remains wired after localized search rendering", async () => {
  const controller = await source("assets/js/modules/dsp-quality/index.js");
  assert.match(controller, /data-quality-mapping-confirm/);
  assert.match(controller, /putTransporterMapping/);
  assert.match(controller, /candidate-selected/);
});

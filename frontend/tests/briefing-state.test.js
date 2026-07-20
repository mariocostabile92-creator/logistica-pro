import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyBriefingEvent,
  createBriefingState,
  deriveBriefingView,
  filterBriefingSections,
} from "../assets/js/modules/briefing-state.js";


const sections = [
  { priority: 3, severity: "information", issue_code: "INFO" },
  { priority: 1, severity: "critical", issue_code: "CRITICAL" },
  { priority: 2, severity: "high", issue_code: "ATTENTION" },
];

const availableBriefing = {
  status: "available",
  attention_level: "attention",
  executive_summary: "Scenario sintetico.",
  sections,
};


test("briefing starts with an accessible loading presentation", () => {
  const view = deriveBriefingView(createBriefingState());

  assert.equal(view.loading, true);
  assert.equal(view.available, false);
  assert.equal(view.error, false);
});


test("empty state uses the typed backend message without an error", () => {
  const state = applyBriefingEvent(createBriefingState(), {
    type: "load-completed",
    briefing: {
      status: "unavailable",
      executive_summary: (
        "Il briefing sarà disponibile dopo la creazione del primo planning."
      ),
      sections: [],
    },
  });
  const view = deriveBriefingView(state);

  assert.equal(view.empty, true);
  assert.equal(
    view.emptyMessage,
    "Il briefing sarà disponibile dopo la creazione del primo planning.",
  );
});


test("available sections always preserve backend priority order", () => {
  const state = applyBriefingEvent(createBriefingState(), {
    type: "load-completed",
    briefing: availableBriefing,
  });

  assert.deepEqual(
    deriveBriefingView(state).sections.map((item) => item.priority),
    [1, 2, 3],
  );
});


test("Home shows at most three priorities until the user expands them", () => {
  const extendedBriefing = {
    ...availableBriefing,
    sections: [
      ...sections,
      { priority: 4, severity: "medium", issue_code: "FOUR" },
      { priority: 5, severity: "low", issue_code: "FIVE" },
    ],
  };
  let state = applyBriefingEvent(createBriefingState(), {
    type: "load-completed",
    briefing: extendedBriefing,
  });
  let view = deriveBriefingView(state);

  assert.equal(view.hasMore, true);
  assert.equal(view.sections.length, 3);
  assert.deepEqual(view.sections.map((item) => item.priority), [1, 2, 3]);

  state = applyBriefingEvent(state, { type: "expanded-toggled" });
  view = deriveBriefingView(state);
  assert.equal(view.expanded, true);
  assert.equal(view.sections.length, 5);
});


test("critical attention and information filters are deterministic", () => {
  assert.deepEqual(
    filterBriefingSections(sections, "critical")
      .map((item) => item.issue_code),
    ["CRITICAL"],
  );
  assert.deepEqual(
    filterBriefingSections(sections, "attention")
      .map((item) => item.issue_code),
    ["ATTENTION"],
  );
  assert.deepEqual(
    filterBriefingSections(sections, "information")
      .map((item) => item.issue_code),
    ["INFO"],
  );
});


test("demo CTA is shown only after demo availability is confirmed", () => {
  let state = createBriefingState({
    phase: "unavailable",
    briefing: { status: "unavailable", sections: [] },
  });
  assert.equal(deriveBriefingView(state).showDemoAction, false);

  state = applyBriefingEvent(state, {
    type: "demo-availability",
    enabled: true,
  });
  assert.equal(deriveBriefingView(state).showDemoAction, true);
});


test("demo reset clears briefing presentation without stale cards", () => {
  const state = applyBriefingEvent(
    createBriefingState({
      phase: "available",
      briefing: availableBriefing,
      filter: "critical",
    }),
    {
      type: "workspace-reset",
      briefing: {
        status: "unavailable",
        executive_summary: (
          "Il briefing sarà disponibile dopo la creazione del primo planning."
        ),
        sections: [],
      },
    },
  );
  const view = deriveBriefingView(state);

  assert.equal(view.empty, true);
  assert.equal(view.sections.length, 0);
  assert.equal(view.selectedFilter, "all");
});


test("unexpected failures produce a dedicated user state", () => {
  const state = applyBriefingEvent(createBriefingState(), {
    type: "load-failed",
    message: "Il briefing non è raggiungibile.",
  });
  const view = deriveBriefingView(state);

  assert.equal(view.error, true);
  assert.equal(view.errorMessage, "Il briefing non è raggiungibile.");
});


test("page includes hero metrics filters empty CTA and live regions", async () => {
  const html = await readFile(
    new URL("../index.html", import.meta.url),
    "utf8",
  );

  assert.match(html, /Cosa richiede la tua attenzione oggi/);
  assert.match(
    html,
    /Il briefing sarà disponibile dopo la creazione del primo planning\./,
  );
  assert.match(html, /Importa dati/);
  assert.match(html, /Carica demo/);
  assert.match(html, /Criticità/);
  assert.match(html, /Azioni consigliate/);
  assert.match(html, /Vedi tutte le criticità/);
  assert.match(html, /data-briefing-filter="critical"/);
  assert.match(html, /data-briefing-filter="attention"/);
  assert.match(html, /data-briefing-filter="information"/);
  assert.match(html, /aria-live="polite"/);
});


test("rendering uses DOM text APIs and exposes sources and action links", async () => {
  const source = await readFile(
    new URL("../assets/js/modules/briefing.js", import.meta.url),
    "utf8",
  );

  assert.match(source, /textContent/);
  assert.match(source, /replaceChildren/);
  assert.match(source, /briefingIssueList/);
  assert.match(source, /Fonti verificate/);
  assert.match(source, /yellow: "Attenzione"/);
  assert.doesNotMatch(source, /Attenzione \(yellow\)/);
  assert.match(source, /workspace:navigate/);
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);
  assert.doesNotMatch(source, /console\.(error|warn)/);
});


test("frontend consumes backend briefing and does not rebuild decisions", async () => {
  const source = await readFile(
    new URL("../assets/js/modules/briefing.js", import.meta.url),
    "utf8",
  );

  assert.match(source, /getLatestDailyBriefing/);
  assert.match(source, /generateDailyBriefing/);
  assert.doesNotMatch(
    source,
    /priority_score|capacity_margin\s*[<>]|reserve_threshold\s*[<>]/,
  );
});


test("briefing CSS defines desktop tablet mobile and reduced-motion behavior", async () => {
  const css = await readFile(
    new URL("../assets/css/briefing.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /overflow-wrap: anywhere/);
});

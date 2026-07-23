import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "../assets/js/modules/mission-control-state.js";


const availableBriefing = {
  status: "available",
  attention_level: "critical",
  attention_reason: "Due interventi richiedono verifica.",
  executive_summary: "La giornata non è ancora pronta.",
  generated_at: "2026-07-22T07:00:00Z",
  planning_id: 12,
  planning_version: 3,
  operational_unit_ids: ["UNIT-A", "UNIT-B"],
  readiness_snapshot: {
    available: true,
    level: "red",
    blocking_issues: 2,
    warnings: 1,
  },
  sections: [
    {
      section_id: "workforce-attention",
      category: "human_resources",
      severity: "high",
      priority: 1,
      title: "Copertura Workforce",
      summary: "Copertura da verificare.",
      facts: [{
        fact_type: "workforce_coverage",
        value: { available: 24, required: 25, margin: -1 },
      }],
      action_links: [{
        label: "Apri Workforce",
        workspace: "workforce",
        target_id: "workforceSection",
      }],
    },
    {
      section_id: "fleet-attention",
      category: "assets",
      severity: "medium",
      priority: 2,
      title: "Stato Asset Registry",
      summary: "Un Asset richiede verifica.",
      facts: [{
        fact_type: "fleet_registry_summary",
        value: {
          total_assets: 27,
          maintenance_assets: 1,
          documents_attention: 2,
        },
      }],
      action_links: [{
        label: "Apri Fleet",
        workspace: "fleet",
        target_id: "fleetPluginSection",
      }],
    },
  ],
};


function availableState() {
  return applyMissionControlEvent(createMissionControlState(), {
    type: "briefing-loaded",
    briefing: availableBriefing,
  });
}


test("initial Mission Control state is explicitly temporary", () => {
  const view = deriveMissionControlView(createMissionControlState());

  assert.equal(view.loading, true);
  assert.equal(view.status.label, "Stato in aggiornamento");
  assert.equal(view.status.temporary, true);
  assert.equal(view.workforce.availabilityLabel, "Dato non esposto");
});


test("day status presents the backend attention level without rebuilding it", () => {
  const view = deriveMissionControlView(availableState());

  assert.equal(view.status.label, "Intervento richiesto");
  assert.equal(view.status.tone, "critical");
  assert.equal(view.status.description, availableBriefing.attention_reason);
  assert.equal(view.status.temporary, false);
});


test("actions preserve backend priority and workspace links", () => {
  const view = deriveMissionControlView(availableState());

  assert.deepEqual(view.actions.map((item) => item.priority), [1, 2]);
  assert.equal(view.actions[0].workspace, "workforce");
  assert.equal(view.actions[0].targetId, "workforceSection");
  assert.equal(view.actions[0].actionLabel, "Apri Workforce");
  assert.equal(view.actions[1].workspace, "fleet");
  assert.equal(view.actions[1].actionLabel, "Apri Fleet");
});


test("empty workspace exposes clearly temporary preparation actions", () => {
  let state = createMissionControlState({
    briefingPhase: "unavailable",
    briefing: {
      status: "unavailable",
      executive_summary: "Nessun Briefing disponibile.",
      sections: [],
      readiness_snapshot: { available: false },
    },
  });
  state = applyMissionControlEvent(state, {
    type: "workspace-loaded",
    workspace: {
      workforce_member_count: 0,
      asset_count: 0,
      planning_count: 0,
    },
  });
  const view = deriveMissionControlView(state);

  assert.equal(view.status.label, "Stato non determinabile");
  assert.equal(view.actions.length, 3);
  assert.ok(view.actions.every((item) => item.temporary));
  assert.deepEqual(
    view.actions.map((item) => item.workspace),
    ["workforce", "fleet", "operations"],
  );
});


test("snapshots consume structured facts and never invent missing Fleet availability", () => {
  const view = deriveMissionControlView(availableState());

  assert.equal(view.workforce.availabilityLabel, "24 su 25");
  assert.equal(view.workforce.absencesLabel, "Dato non esposto");
  assert.equal(view.fleet.maintenanceLabel, "1");
  assert.equal(view.fleet.documentsLabel, "2 in attenzione");
  assert.equal(view.fleet.availableLabel, "Dato non esposto");
  assert.equal(view.planning.readiness, "Critica");
  assert.equal(view.planning.conflictsLabel, "2 bloccanti · 1 avvisi");
});


test("Operational Unit supports aggregate and multiple options without fake filtering", () => {
  const view = deriveMissionControlView(availableState());

  assert.equal(view.operationalUnits.selected, "all");
  assert.equal(view.operationalUnits.disabled, true);
  assert.deepEqual(
    view.operationalUnits.options.map((item) => item.value),
    ["all", "UNIT-A", "UNIT-B"],
  );
});


test("timeline uses only existing Workspace and Briefing timestamps", () => {
  const state = applyMissionControlEvent(availableState(), {
    type: "workspace-loaded",
    workspace: {
      latest_planning_import: {
        import_id: 1,
        imported_at: "2026-07-22T06:30:00Z",
      },
      latest_fleet_import: {
        import_id: 2,
        imported_at: "2026-07-22T06:40:00Z",
      },
      last_operational_update: "2026-07-22T06:55:00Z",
    },
  });
  const labels = deriveMissionControlView(state).timeline.map((item) => item.label);

  assert.deepEqual(labels, [
    "Briefing aggiornato",
    "Workspace operativo aggiornato",
    "Sincronizzazione parco mezzi disponibile",
    "Import del Planning completato",
  ]);
});


test("Home contains the definitive Mission Control hierarchy", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

  const expectedOrder = [
    "missionControlTitle",
    "missionDayStatus",
    "missionActionsTitle",
    "missionSnapshotsTitle",
    "missionTimelineTitle",
    "briefingTitle",
  ];
  let previousIndex = -1;
  for (const marker of expectedOrder) {
    const currentIndex = html.indexOf(marker);
    assert.ok(currentIndex > previousIndex, `${marker} must preserve Mission Control order`);
    previousIndex = currentIndex;
  }
  assert.match(html, /data-mission-workspace="workforce"/);
  assert.match(html, /data-mission-workspace="fleet"/);
  assert.match(html, /data-mission-workspace="operations"/);
  assert.match(html, /aria-live="polite"/);
});


test("Mission Control is responsive and does not introduce direct API calls", async () => {
  const [css, source] = await Promise.all([
    readFile(new URL("../assets/css/mission-control.css", import.meta.url), "utf8"),
    readFile(new URL("../assets/js/modules/mission-control.js", import.meta.url), "utf8"),
  ]);

  assert.match(css, /@media \(max-width: 1100px\)/);
  assert.match(css, /@media \(max-width: 820px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /mission-control-source/);
  assert.doesNotMatch(source, /fetch\(|getLatest|generateDaily|console\.(error|warn)/);
  assert.match(source, /briefing:changed/);
  assert.match(source, /workspace:status-changed/);
});


test("Mission Control mobile keeps actions primary and compacts secondary blocks", async () => {
  const css = await readFile(
    new URL("../assets/css/mission-control.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /@media \(max-width: 620px\)[\s\S]*?\.mission-action-row[\s\S]*?padding: 11px 12px/,
  );
  assert.match(
    css,
    /@media \(max-width: 620px\)[\s\S]*?\.mission-timeline-list[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(css, /\.mission-briefing \.briefing-summary[\s\S]*?-webkit-line-clamp: 2/);
});


test("Mission Control P1 keeps ownership explicit and secondary context compact", async () => {
  const [html, css, state] = await Promise.all([
    readFile(new URL("../index.html", import.meta.url), "utf8"),
    readFile(new URL("../assets/css/mission-control.css", import.meta.url), "utf8"),
    readFile(
      new URL("../assets/js/modules/mission-control-state.js", import.meta.url),
      "utf8",
    ),
  ]);

  assert.match(
    html,
    /data-mission-workspace="operations"[\s\S]*?Apri Planning/,
  );
  assert.match(state, /operations: "Apri Planning"/);
  assert.match(state, /fleet: "Apri Fleet"/);
  assert.match(state, /workforce: "Apri Workforce"/);
  assert.match(css, /\.mission-snapshot[\s\S]*?padding: 12px 14px 10px/);
  assert.match(css, /\.mission-timeline[\s\S]*?margin-top: 22px/);
  assert.match(css, /\.mission-briefing[\s\S]*?margin: 22px 0 0/);
});

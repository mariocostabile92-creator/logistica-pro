import { byId } from "../utils/dom.js";


function localizedTimestamp(value) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT");
}


function appendFact(list, label, value) {
  if (value === null || value === undefined || value === "") return;
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const definition = document.createElement("dd");
  term.textContent = label;
  definition.textContent = String(value);
  row.append(term, definition);
  list.append(row);
}


function setAction(action, visible, label = null) {
  const button = byId("workspaceCardActions").querySelector(
    `[data-workspace-action="${action}"]`,
  );
  button.hidden = !visible;
  if (label) button.textContent = label;
}


export function renderWorkspaceCard(view) {
  const card = byId("workspaceCurrentCard");
  const loading = byId("workspaceCardLoading");
  const empty = byId("workspaceCardEmpty");
  const facts = byId("workspaceCardFacts");
  const badge = byId("workspaceCardBadge");

  card.className = `workspace-current-card ${view.tone}`;
  card.setAttribute("aria-busy", String(view.loading));
  badge.className = `workspace-card-badge ${view.tone}`;
  badge.textContent = view.shortLabel;
  loading.hidden = !view.loading;
  facts.replaceChildren();

  const status = view.status;
  empty.hidden = !status || status.workspace_state !== "EMPTY";
  if (status && status.workspace_state !== "EMPTY") {
    const planning = status.latest_planning_import;
    const fleet = status.latest_fleet_import;
    appendFact(facts, "File Planning", planning?.original_filename);
    appendFact(facts, "Import Planning", localizedTimestamp(planning?.imported_at));
    appendFact(facts, "File Fleet", fleet?.original_filename);
    appendFact(facts, "Import Fleet", localizedTimestamp(fleet?.imported_at));
    appendFact(facts, "Task", status.task_count);
    appendFact(facts, "Asset", status.asset_count);
    appendFact(facts, "Workforce", status.workforce_member_count || 0);
    appendFact(facts, "Planning", status.planning_count);
    appendFact(facts, "Briefing", status.briefing_count);
    appendFact(
      facts,
      "Ultimo aggiornamento",
      localizedTimestamp(status.last_operational_update),
    );
  }

  const actions = view.actions;
  setAction("import", actions.import, view.importLabel);
  setAction("load-demo", actions.loadDemo);
  setAction("new-day", actions.newDay);
  setAction("reset", actions.reset);
}

import { byId } from "../utils/dom.js";


function setAction(action, visible, label = null) {
  const button = byId("workspaceHeaderActions").querySelector(
    `[data-workspace-action="${action}"]`,
  );
  button.hidden = !visible;
  if (label) button.textContent = label;
}


export function renderWorkspaceHeader(view) {
  const badge = byId("workspaceStatusBadge");
  badge.className = `workspace-status-badge ${view.tone}`;
  byId("workspaceStatusLabel").textContent = view.label;
  byId("workspaceMenuTitle").textContent = view.label;
  byId("workspaceMenuDescription").textContent = view.description;

  const actions = view.actions;
  setAction("import", actions.import, view.importLabel);
  setAction("load-demo", actions.loadDemo);
  setAction("new-day", actions.newDay);
  setAction("reset", actions.reset);
}

import {
  createConflictSummary,
  createDraftPlaceholder,
  createFooterActions,
  createPlanningHeader,
  createPlanningLoadingState,
  createPublicationPlaceholder,
  createReadinessCard,
  createStatusCard,
  createTimelinePlaceholder,
} from "./components.js";
import { element } from "./utils.js";


export function createPlanningWorkspaceLayout(root) {
  const shell = element("div", { className: "planning-workspace-shell" });
  const header = createPlanningHeader();
  const loading = createPlanningLoadingState();
  const content = element("div", {
    className: "planning-workspace-content",
    attributes: { "data-planning-role": "content" },
  });
  content.append(
    createStatusCard(),
    createReadinessCard(),
    createConflictSummary(),
    createTimelinePlaceholder(),
    createDraftPlaceholder(),
    createPublicationPlaceholder(),
    createFooterActions(),
  );
  shell.append(header, loading, content);
  root.replaceChildren(shell);

  const role = (name) => root.querySelector(`[data-planning-role="${name}"]`);
  return Object.freeze({
    root,
    loading,
    content,
    badge: role("badge"),
    date: role("date"),
    unit: role("unit"),
    statusTitle: role("status-title"),
    statusDescription: role("status-description"),
    readinessValue: role("readiness-value"),
    readinessDetail: role("readiness-detail"),
    conflictsValue: role("conflicts-value"),
    conflictsDetail: role("conflicts-detail"),
    timelineValue: role("timeline-value"),
    timelineDetail: role("timeline-detail"),
    draftValue: role("draft-value"),
    draftDetail: role("draft-detail"),
    publicationValue: role("publication-value"),
    publicationDetail: role("publication-detail"),
    actions: role("actions"),
    legacyButton: root.querySelector('[data-planning-action="open-legacy"]'),
    confirmButton: root.querySelector('[data-planning-action="confirm"]'),
  });
}

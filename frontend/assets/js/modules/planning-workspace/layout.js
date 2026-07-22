import {
  createConflictSummary,
  createDraftPlaceholder,
  createFooterActions,
  createPlanningHeader,
  createPlanningLoadingState,
  createPlanningTimeline,
  createPublicationPlaceholder,
  createReadinessCard,
  createStatusCard,
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
    createPlanningTimeline(),
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
    retryButton: root.querySelector('[data-planning-action="retry-conflicts"]'),
    readinessValue: role("readiness-value"),
    readinessDetail: role("readiness-detail"),
    readinessBlockers: role("readiness-blockers"),
    readinessBlockerList: role("readiness-blocker-list"),
    readinessWarnings: role("readiness-warnings"),
    readinessWarningList: role("readiness-warning-list"),
    readinessMetadata: role("readiness-metadata"),
    readinessUnit: role("readiness-unit"),
    readinessDate: role("readiness-date"),
    readinessUpdated: role("readiness-updated"),
    readinessLegacy: role("readiness-legacy"),
    conflictBody: role("conflict-body"),
    conflictTotal: role("conflict-total"),
    conflictBlocking: role("conflict-blocking"),
    conflictWarnings: role("conflict-warnings"),
    conflictEmpty: role("conflict-empty"),
    conflictGroups: role("conflict-groups"),
    conflictTop: role("conflict-top"),
    conflictList: role("conflict-list"),
    conflictTitle: root.querySelector("#planningWorkspaceConflictsTitle"),
    timelineBody: role("timeline-body"),
    timelineCount: role("timeline-count"),
    timelineStatus: role("timeline-status"),
    timelineUpdated: role("timeline-updated"),
    timelineLoading: role("timeline-loading"),
    timelineEmpty: role("timeline-empty"),
    timelineError: role("timeline-error"),
    timelineErrorText: role("timeline-error-text"),
    timelineGroups: role("timeline-groups"),
    draftValue: role("draft-value"),
    draftDetail: role("draft-detail"),
    publicationValue: role("publication-value"),
    publicationDetail: role("publication-detail"),
    actions: role("actions"),
    legacyButton: root.querySelector('[data-planning-action="open-legacy"]'),
    confirmButton: root.querySelector('[data-planning-action="confirm"]'),
  });
}

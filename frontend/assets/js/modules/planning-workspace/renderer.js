import {
  element,
  formatPlanningDate,
  formatPlanningTimestamp,
  setNodeText,
} from "./utils.js";


function renderPlaceholder(refs, name, value) {
  setNodeText(refs[`${name}Value`], value.value);
  setNodeText(refs[`${name}Detail`], value.detail);
}


function renderIssues(container, list, issues = []) {
  const nodes = issues.map((issue) => {
    const item = element("li");
    item.append(
      element("strong", { text: issue.message || issue.code || "Dato da verificare" }),
    );
    if (issue.remediationHint) {
      item.append(element("p", { text: issue.remediationHint }));
    }
    return item;
  });
  list.replaceChildren(...nodes);
  container.hidden = nodes.length === 0;
}


function renderReadiness(refs, readiness) {
  renderPlaceholder(refs, "readiness", readiness);
  const available = Number.isInteger(readiness.score);
  renderIssues(refs.readinessBlockers, refs.readinessBlockerList, readiness.blockers);
  renderIssues(refs.readinessWarnings, refs.readinessWarningList, readiness.warnings);
  refs.readinessMetadata.hidden = !available;
  setNodeText(refs.readinessUnit, readiness.operationalUnit || "Non disponibile");
  setNodeText(refs.readinessDate, formatPlanningDate(readiness.planningDate));
  setNodeText(refs.readinessUpdated, formatPlanningTimestamp(readiness.evaluatedAt));
  setNodeText(
    refs.readinessLegacy,
    readiness.legacyFlowActive === true ? "Attivo" : "Non attivo",
  );
}


export function renderPlanningWorkspace(refs, view) {
  refs.root.dataset.planningWorkspaceState = view.state;
  refs.root.dataset.planningWorkspaceTone = view.tone;
  refs.root.setAttribute("aria-busy", String(view.loading));
  refs.loading.hidden = !view.loading;
  refs.content.hidden = view.loading;
  document.body.dataset.planningWorkspaceState = view.state;

  setNodeText(refs.badge, view.badge);
  setNodeText(refs.date, formatPlanningDate(view.planningDate));
  setNodeText(refs.unit, view.operationalUnit || "Tutte");
  setNodeText(refs.statusTitle, view.statusTitle);
  setNodeText(refs.statusDescription, view.statusDescription);
  renderReadiness(refs, view.readiness);
  renderPlaceholder(refs, "conflicts", view.conflicts);
  renderPlaceholder(refs, "timeline", view.timeline);
  renderPlaceholder(refs, "draft", view.draft);
  renderPlaceholder(refs, "publication", view.publication);
  refs.confirmButton.disabled = !view.canConfirm;
  refs.retryButton.hidden = !view.canRetry;
}

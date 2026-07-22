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


function conflictBadge(value, className = "") {
  return element("span", {
    className: `planning-conflict-badge ${className}`.trim(),
    text: value,
  });
}


function renderConflictGroups(refs, report) {
  const conflictsById = new Map(
    report.conflicts.map((conflict) => [conflict.id, conflict]),
  );
  const nodes = report.groups.map((group, index) => {
    const details = element("details", {
      className: "planning-conflict-group",
      attributes: {
        "data-conflict-category": group.category,
        ...(index === 0 && group.totalBlocking ? { open: "" } : {}),
      },
    });
    const summary = element("summary", {
      attributes: {
        "aria-label": `${group.label}: ${group.totalConflicts} conflitti`,
      },
    });
    const labels = element("span");
    labels.append(
      element("strong", { text: group.label }),
      element("span", {
        text: `${group.totalConflicts} totali`,
      }),
    );
    summary.append(labels);
    if (group.totalBlocking) {
      summary.append(conflictBadge(
        `${group.totalBlocking} bloccanti`,
        "critical",
      ));
    } else {
      summary.append(conflictBadge(group.highestSeverity));
    }
    const list = element("ul");
    const items = group.conflictIds
      .map((id) => conflictsById.get(id))
      .filter(Boolean)
      .map((conflict) => element("li", { text: conflict.title }));
    list.append(...items);
    details.append(summary, list);
    return details;
  });
  refs.conflictGroups.replaceChildren(...nodes);
  refs.conflictGroups.hidden = nodes.length === 0;
}


function renderConflictList(refs, report) {
  const nodes = report.topConflicts.map((conflict) => {
    const item = element("li", {
      className: `planning-conflict-item ${conflict.blocking ? "blocking" : "warning"}`,
    });
    const meta = element("div", { className: "planning-conflict-item-meta" });
    meta.append(
      conflictBadge(conflict.severity, conflict.blocking ? "critical" : ""),
      element("span", { text: conflict.category.replaceAll("_", " ") }),
    );
    item.append(
      meta,
      element("h5", { text: conflict.title }),
      element("p", { text: conflict.description }),
      element("p", {
        className: "planning-conflict-action",
        text: `Azione: ${conflict.suggestion.action}`,
      }),
    );
    return item;
  });
  refs.conflictList.replaceChildren(...nodes);
  refs.conflictTop.hidden = nodes.length === 0;
}


function renderConflicts(refs, report) {
  const available = report && Number.isInteger(report.totalConflicts);
  setNodeText(refs.conflictTotal, available ? report.totalConflicts : "-");
  setNodeText(refs.conflictBlocking, available ? report.totalBlocking : "-");
  setNodeText(refs.conflictWarnings, available ? report.totalWarnings : "-");
  refs.conflictEmpty.hidden = available && report.totalConflicts > 0;
  setNodeText(
    refs.conflictEmpty,
    available
      ? "Nessun conflitto rilevato."
      : "Conflict Review non disponibile.",
  );
  if (!available) {
    refs.conflictGroups.replaceChildren();
    refs.conflictGroups.hidden = true;
    refs.conflictList.replaceChildren();
    refs.conflictTop.hidden = true;
    return;
  }
  renderConflictGroups(refs, report);
  renderConflictList(refs, report);
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
  renderConflicts(refs, view.conflicts);
  renderPlaceholder(refs, "timeline", view.timeline);
  renderPlaceholder(refs, "draft", view.draft);
  renderPlaceholder(refs, "publication", view.publication);
  refs.confirmButton.disabled = !view.canConfirm;
  refs.retryButton.hidden = !view.canRetry;
}

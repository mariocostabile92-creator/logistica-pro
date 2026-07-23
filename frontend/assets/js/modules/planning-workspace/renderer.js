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
  setNodeText(refs.readinessUnit, readiness.operationalUnit || "Non indicata");
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
      : "Verifica conflitti non disponibile.",
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


const TIMELINE_MARKERS = Object.freeze({
  IMPORT: "I",
  VALIDATION: "V",
  WORKFORCE: "W",
  FLEET: "F",
  READINESS: "R",
  CONFLICT: "!",
  RUNTIME: "RT",
  SYSTEM: "S",
  LEGACY: "L",
});


function timelineEventNode(event) {
  const item = element("li", {
    className: `planning-timeline-event severity-${event.severity.toLowerCase()}`,
    attributes: {
      tabindex: "0",
      "data-timeline-category": event.category,
      "aria-label": `${event.category}: ${event.title}`,
    },
  });
  const marker = element("span", {
    className: "planning-timeline-marker",
    text: TIMELINE_MARKERS[event.category] || "i",
    attributes: { "aria-hidden": "true" },
  });
  const content = element("div", { className: "planning-timeline-event-content" });
  const meta = element("div", { className: "planning-timeline-event-meta" });
  meta.append(
    element("time", {
      text: formatPlanningTimestamp(event.timestamp),
      attributes: { datetime: event.timestamp },
    }),
    element("span", {
      className: "planning-timeline-category",
      text: event.category,
    }),
    element("span", {
      className: `planning-timeline-status severity-${event.severity.toLowerCase()}`,
      text: event.status,
    }),
  );
  content.append(
    meta,
    element("h5", { text: event.title }),
    element("p", { text: event.description }),
  );
  if (event.relatedConflicts.length) {
    content.append(element("a", {
      className: "planning-timeline-conflict-link",
      text: `Apri conflitti (${event.relatedConflicts.length})`,
      attributes: {
        href: "#planningWorkspaceConflictsTitle",
        "data-planning-action": "view-conflicts",
      },
    }));
  }
  item.append(marker, content);
  return item;
}


function renderTimelineGroups(refs, timeline) {
  const eventsById = new Map(
    timeline.events.map((event) => [event.id, event]),
  );
  const groups = timeline.groups.map((group) => {
    const titleId = `planningTimelineGroup-${group.key}`;
    const section = element("section", {
      className: "planning-timeline-group",
      attributes: { "aria-labelledby": titleId },
    });
    section.append(element("h4", {
      text: `${group.label} (${group.eventCount})`,
      attributes: { id: titleId },
    }));
    const list = element("ol");
    list.append(
      ...group.eventIds
        .map((eventId) => eventsById.get(eventId))
        .filter(Boolean)
        .map(timelineEventNode),
    );
    section.append(list);
    return section;
  });
  refs.timelineGroups.replaceChildren(...groups);
  refs.timelineGroups.hidden = groups.length === 0;
}


function renderTimeline(refs, timeline) {
  const loading = timeline?.state === "loading";
  const empty = timeline?.state === "empty";
  const failed = timeline?.state === "error";
  const ready = timeline?.state === "ready";
  refs.timelineBody.setAttribute("aria-busy", String(loading));
  refs.timelineLoading.hidden = !loading;
  refs.timelineEmpty.hidden = !empty;
  refs.timelineError.hidden = !failed;
  setNodeText(
    refs.timelineErrorText,
    timeline?.message || "Cronologia del piano non disponibile.",
  );
  setNodeText(refs.timelineCount, ready || empty ? timeline.eventCount : "-");
  setNodeText(
    refs.timelineStatus,
    ready || empty ? timeline.currentStatus : "Non determinato",
  );
  setNodeText(
    refs.timelineUpdated,
    ready || empty
      ? formatPlanningTimestamp(timeline.lastUpdated)
      : "Non registrato",
  );
  if (ready) {
    renderTimelineGroups(refs, timeline);
    return;
  }
  refs.timelineGroups.replaceChildren();
  refs.timelineGroups.hidden = true;
}


const DRAFT_STATE_LABELS = Object.freeze({
  CREATED: "Creato",
  DIRTY: "Modificato",
  SAVED: "Salvato",
  READ_ONLY: "Sola lettura",
});


function renderDraftHistory(refs, history) {
  const changes = history?.changes || [];
  const nodes = changes.slice(0, 5).map((change) => {
    const item = element("li", {
      attributes: {
        tabindex: "0",
        "aria-label": `Versione ${change.toVersion}: ${change.summary}`,
      },
    });
    const meta = element("div", { className: "planning-draft-history-meta" });
    meta.append(
      element("strong", { text: `v${change.toVersion}` }),
      element("time", {
        text: formatPlanningTimestamp(change.occurredAt),
        attributes: { datetime: change.occurredAt },
      }),
    );
    item.append(meta, element("p", { text: change.summary }));
    return item;
  });
  refs.draftHistoryList.replaceChildren(...nodes);
  refs.draftHistory.hidden = nodes.length === 0;
}


function renderDraftRestoreOptions(refs, draft) {
  const snapshots = (draft.history?.snapshots || []).filter(
    (snapshot) => snapshot.version.number < draft.draft.version.number,
  );
  refs.draftRestoreSelect.replaceChildren(
    ...snapshots.map((snapshot) => element("option", {
      text: `v${snapshot.version.number} - ${snapshot.name}`,
      attributes: { value: String(snapshot.version.number) },
    })),
  );
  refs.draftRestore.hidden = !snapshots.length || draft.busy;
  refs.draftRestoreButton.disabled = !snapshots.length || draft.busy;
}


function renderDraft(refs, draft) {
  const loading = draft?.viewState === "loading";
  const failed = draft?.viewState === "error";
  const hasDraft = Boolean(draft?.draft);
  const readOnly = draft?.state === "READ_ONLY";
  const empty = draft?.viewState === "empty" || readOnly;
  refs.draftBody.setAttribute("aria-busy", String(loading || draft?.busy === true));
  refs.draftLoading.hidden = !loading;
  refs.draftError.hidden = !failed;
  setNodeText(
    refs.draftErrorText,
    draft?.message || "Bozza di pianificazione non disponibile.",
  );
  refs.draftSummary.hidden = !hasDraft;
  refs.draftEmpty.hidden = !empty;
  setNodeText(
    refs.draftEmpty,
    readOnly
      ? "Bozza eliminata. La cronologia resta disponibile in sola lettura."
      : "Nessuna bozza disponibile. Crea una proposta separata dal piano operativo.",
  );
  refs.draftEditor.hidden = loading || (failed && !hasDraft);

  if (hasDraft) {
    setNodeText(refs.draftSummaryName, draft.draft.name);
    setNodeText(
      refs.draftSummaryState,
      DRAFT_STATE_LABELS[draft.state] || draft.state,
    );
    setNodeText(refs.draftSummaryVersion, `v${draft.draft.version.number}`);
    setNodeText(
      refs.draftSummaryUpdated,
      formatPlanningTimestamp(draft.draft.updatedAt),
    );
  }

  const renderKey = hasDraft
    ? `${draft.draft.id}:${draft.draft.version.number}`
    : "empty";
  if (refs.draftEditor.dataset.renderKey !== renderKey) {
    refs.draftNameInput.value = hasDraft ? draft.draft.name : "";
    refs.draftNoteInput.value = hasDraft ? draft.draft.note : "";
    refs.draftEditor.dataset.renderKey = renderKey;
  }
  refs.draftNameInput.disabled = draft?.busy === true;
  refs.draftNoteInput.disabled = draft?.busy === true;
  refs.draftCreateButton.hidden = hasDraft && !readOnly;
  refs.draftCreateButton.disabled =
    draft?.busy === true || !refs.draftNameInput.value.trim();
  refs.draftSaveButton.hidden = !hasDraft || readOnly;
  refs.draftSaveButton.disabled = draft?.busy === true
    || draft?.state === "SAVED";
  refs.draftDeleteRow.hidden = !hasDraft || readOnly;
  refs.draftDeleteButton.disabled = draft?.busy === true;
  refs.draftDeleteConfirm.hidden = true;
  refs.draftFeedback.hidden = !draft?.feedback;
  setNodeText(refs.draftFeedback, draft?.feedback || "");

  if (hasDraft) {
    renderDraftRestoreOptions(refs, draft);
    renderDraftHistory(refs, draft.history);
  } else {
    refs.draftRestore.hidden = true;
    refs.draftHistory.hidden = true;
    refs.draftHistoryList.replaceChildren();
  }
}


const CONFIRMATION_STATE_LABELS = Object.freeze({
  NOT_READY: "Non confermabile",
  READY_TO_CONFIRM: "Pronto per la conferma",
  CONFIRMED: "Confermato",
  REJECTED: "Conferma rifiutata",
  ERROR: "Errore",
});


function confirmationRuleNode(rule) {
  const item = element("li", {
    attributes: { tabindex: "0" },
  });
  item.append(element("strong", { text: rule.reason }));
  if (!rule.passed) {
    item.append(element("p", { text: rule.remediationHint }));
  }
  return item;
}


function renderConfirmationRules(refs, result) {
  const passed = result.rules.filter((rule) => rule.passed);
  const failed = result.rules.filter((rule) => !rule.passed);
  refs.confirmationPassedList.replaceChildren(
    ...passed.map(confirmationRuleNode),
  );
  refs.confirmationFailedList.replaceChildren(
    ...failed.map(confirmationRuleNode),
  );
  refs.confirmationPassed.hidden = passed.length === 0;
  refs.confirmationFailed.hidden = failed.length === 0;
  setNodeText(refs.confirmationPassedCount, passed.length);
  setNodeText(refs.confirmationFailedCount, failed.length);
}


function renderConfirmationHistory(refs, history) {
  const nodes = (history?.confirmations || []).slice(0, 5).map((item) => {
    const node = element("li", {
      attributes: {
        tabindex: "0",
        "aria-label": `${item.draftName}, confermato ${formatPlanningTimestamp(item.confirmedAt)}`,
      },
    });
    const meta = element("div", {
      className: "planning-confirmation-history-meta",
    });
    meta.append(
      element("strong", { text: item.draftName }),
      element("time", {
        text: formatPlanningTimestamp(item.confirmedAt),
        attributes: { datetime: item.confirmedAt },
      }),
    );
    node.append(
      meta,
      element("p", {
        text: `Bozza v${item.draftVersion} · Preparazione ${item.readinessScore}/100`,
      }),
    );
    return node;
  });
  refs.confirmationHistoryList.replaceChildren(...nodes);
  refs.confirmationHistory.hidden = nodes.length === 0;
}


function renderConfirmation(refs, confirmation, draftWorkspace) {
  const loading = confirmation?.viewState === "loading";
  const failed = confirmation?.viewState === "error";
  const result = confirmation?.result || null;
  const current = confirmation?.current || null;
  const draft = draftWorkspace?.draft || null;
  const busy = confirmation?.busy === true;
  refs.confirmationBody.dataset.confirmationState = result?.state || "LOADING";
  refs.confirmationBody.setAttribute("aria-busy", String(loading || busy));
  refs.confirmationLoading.hidden = !loading;
  refs.confirmationError.hidden = !failed;
  setNodeText(
    refs.confirmationErrorText,
    confirmation?.message || "Conferma del piano non disponibile.",
  );
  refs.confirmationSummary.hidden = loading;
  refs.confirmationValidation.hidden = !result || loading;
  refs.confirmationRationale.hidden = !result || loading;
  setNodeText(
    refs.confirmationState,
    result ? CONFIRMATION_STATE_LABELS[result.state] || result.state : "Non disponibile",
  );
  setNodeText(
    refs.confirmationDraft,
    current?.draftName || draft?.name || "Nessuna bozza",
  );
  setNodeText(
    refs.confirmationVersion,
    current
      ? `Conferma v${current.version} · Bozza v${current.draftVersion}`
      : draft ? `Bozza v${draft.version.number}` : "-",
  );
  setNodeText(
    refs.confirmationUpdated,
    result ? formatPlanningTimestamp(result.evaluatedAt) : "-",
  );
  setNodeText(refs.confirmationRationale, result?.rationale || "");
  if (result) renderConfirmationRules(refs, result);
  else {
    refs.confirmationPassedList.replaceChildren();
    refs.confirmationFailedList.replaceChildren();
  }

  refs.confirmationFeedback.hidden = !confirmation?.feedback;
  setNodeText(refs.confirmationFeedback, confirmation?.feedback || "");
  refs.confirmationActions.hidden = loading || (failed && !result);
  refs.confirmationValidateButton.disabled = busy || !draft || Boolean(current);
  refs.confirmationBeginButton.disabled = busy || failed || !result?.canConfirm;
  refs.confirmationBeginButton.textContent = current
    ? "Piano confermato"
    : "Conferma piano";
  refs.confirmationHint.hidden = loading;
  setNodeText(
    refs.confirmationHint,
    current
      ? "Il piano confermato è immutabile. La pubblicazione non è ancora disponibile."
      : result?.canConfirm
        ? "Tutte le regole sono superate. La conferma non pubblica il piano."
        : result?.rationale || "Completa la bozza e ripeti la verifica.",
  );
  refs.confirmationExplicit.hidden = true;
  refs.confirmationConfirmButton.disabled = busy || !result?.canConfirm;
  renderConfirmationHistory(refs, confirmation?.history);
}


const PUBLICATION_STATE_LABELS = Object.freeze({
  NOT_PUBLISHED: "Non pubblicato",
  READY_TO_PUBLISH: "Pronto per la pubblicazione",
  PUBLISHED: "Pubblicato",
  FAILED: "Pubblicazione rifiutata",
  ERROR: "Errore",
});


function publicationRuleNode(rule) {
  const item = element("li", { attributes: { tabindex: "0" } });
  item.append(element("strong", { text: rule.reason }));
  if (!rule.passed) {
    item.append(element("p", { text: rule.remediationHint }));
  }
  return item;
}


function renderPublicationRules(refs, result) {
  const passed = result.rules.filter((rule) => rule.passed);
  const failed = result.rules.filter((rule) => !rule.passed);
  refs.publicationPassedList.replaceChildren(
    ...passed.map(publicationRuleNode),
  );
  refs.publicationFailedList.replaceChildren(
    ...failed.map(publicationRuleNode),
  );
  refs.publicationPassed.hidden = passed.length === 0;
  refs.publicationFailed.hidden = failed.length === 0;
  setNodeText(refs.publicationPassedCount, passed.length);
  setNodeText(refs.publicationFailedCount, failed.length);
}


function renderPublicationHistory(refs, history) {
  const nodes = (history?.publications || []).slice(0, 5).map((item) => {
    const node = element("li", {
      attributes: {
        tabindex: "0",
        "aria-label": `Pubblicazione versione ${item.version}, ${formatPlanningTimestamp(item.publishedAt)}`,
      },
    });
    const meta = element("div", {
      className: "planning-publication-history-meta",
    });
    meta.append(
      element("strong", { text: `Pubblicazione v${item.version}` }),
      element("time", {
        text: formatPlanningTimestamp(item.publishedAt),
        attributes: { datetime: item.publishedAt },
      }),
    );
    node.append(
      meta,
      element("p", {
        text: `Piano confermato v${item.confirmationVersion} · ${item.actor}`,
      }),
    );
    return node;
  });
  refs.publicationHistoryList.replaceChildren(...nodes);
  refs.publicationHistory.hidden = nodes.length === 0;
}


function renderPublication(refs, publication, confirmationWorkspace) {
  const loading = publication?.viewState === "loading";
  const failed = publication?.viewState === "error";
  const result = publication?.result || null;
  const current = publication?.current || null;
  const confirmation = confirmationWorkspace?.current || null;
  const busy = publication?.busy === true;
  refs.publicationBody.dataset.publicationState = result?.state || "LOADING";
  refs.publicationBody.setAttribute("aria-busy", String(loading || busy));
  refs.publicationLoading.hidden = !loading;
  refs.publicationError.hidden = !failed;
  setNodeText(
    refs.publicationErrorText,
    publication?.message || "Pubblicazione del piano non disponibile.",
  );
  refs.publicationSummary.hidden = loading;
  refs.publicationValidation.hidden = !result || loading;
  refs.publicationRationale.hidden = !result || loading;
  setNodeText(
    refs.publicationState,
    result ? PUBLICATION_STATE_LABELS[result.state] || result.state : "Non disponibile",
  );
  setNodeText(
    refs.publicationVersion,
    current ? `Pubblicazione v${current.version}` : "-",
  );
  setNodeText(
    refs.publicationUpdated,
    current ? formatPlanningTimestamp(current.publishedAt) : "-",
  );
  setNodeText(refs.publicationActor, current?.actor || "-");
  setNodeText(
    refs.publicationConfirmation,
    current
      ? `v${current.confirmationVersion} · ${current.confirmationId}`
      : confirmation ? `v${confirmation.version} · ${confirmation.id}` : "Nessuno",
  );
  setNodeText(
    refs.publicationFingerprint,
    current?.fingerprint || confirmation?.fingerprint || "-",
  );
  setNodeText(refs.publicationRationale, result?.rationale || "");
  if (result) renderPublicationRules(refs, result);
  else {
    refs.publicationPassedList.replaceChildren();
    refs.publicationFailedList.replaceChildren();
  }
  refs.publicationFeedback.hidden = !publication?.feedback;
  setNodeText(refs.publicationFeedback, publication?.feedback || "");
  refs.publicationActions.hidden = loading || (failed && !result);
  refs.publicationValidateButton.disabled = (
    busy || !confirmation || Boolean(current)
  );
  refs.publicationBeginButton.disabled = (
    busy || failed || !confirmation || !result?.canPublish
  );
  refs.publicationBeginButton.textContent = current
    ? "Piano pubblicato"
    : "Pubblica piano";
  refs.publicationHint.hidden = loading;
  setNodeText(
    refs.publicationHint,
    current
      ? "Il piano pubblicato è immutabile. Nessuna esecuzione è stata avviata."
      : result?.canPublish
        ? "Tutte le regole sono superate. La pubblicazione non esegue il piano."
        : result?.rationale || "Conferma la bozza e ripeti la verifica.",
  );
  refs.publicationExplicit.hidden = true;
  refs.publicationPublishButton.disabled = (
    busy || !confirmation || !result?.canPublish
  );
  renderPublicationHistory(refs, publication?.history);
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
  renderTimeline(refs, view.timeline);
  renderDraft(refs, view.draft);
  renderConfirmation(refs, view.confirmation, view.draft);
  renderPublication(refs, view.publication, view.confirmation);
  refs.retryButton.hidden = !view.canRetry;
}

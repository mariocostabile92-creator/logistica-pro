import { element } from "./utils.js";


function textBlock(role, className) {
  return element("p", {
    className,
    attributes: { "data-planning-role": role },
  });
}


export function createPlanningHeader() {
  const header = element("header", { className: "planning-workspace-header" });
  const heading = element("div", { className: "planning-workspace-heading" });
  heading.append(
    element("p", { className: "eyebrow", text: "Pianificazione operativa" }),
    element("h2", {
      text: "Planning operativo",
      attributes: { id: "planningWorkspaceTitle" },
    }),
    element("p", {
      className: "planning-workspace-question",
      text: "Il piano operativo di oggi è pronto per essere confermato?",
    }),
  );
  const context = element("dl", {
    className: "planning-workspace-context",
    attributes: { "aria-label": "Contesto Planning" },
  });
  const date = element("div");
  date.append(
    element("dt", { text: "Data" }),
    element("dd", { attributes: { "data-planning-role": "date" } }),
  );
  const unit = element("div");
  unit.append(
    element("dt", { text: "Unità operativa" }),
    element("dd", { attributes: { "data-planning-role": "unit" } }),
  );
  context.append(date, unit);
  header.append(heading, context);
  return header;
}


export function createStatusCard() {
  const card = element("section", {
    className: "planning-workspace-status",
    attributes: {
      "data-planning-component": "status",
      "aria-labelledby": "planningWorkspaceStatusTitle",
    },
  });
  const copy = element("div");
  copy.append(
    element("span", {
      className: "planning-workspace-badge",
      attributes: { "data-planning-role": "badge" },
    }),
    element("h3", {
      attributes: {
        id: "planningWorkspaceStatusTitle",
        "data-planning-role": "status-title",
      },
    }),
    textBlock("status-description", "planning-workspace-description"),
  );
  const retry = element("button", {
    className: "secondary planning-workspace-retry",
    text: "Riprova",
    attributes: {
      type: "button",
      "data-planning-action": "retry-conflicts",
      hidden: "",
      "aria-label": "Riprova il caricamento della verifica conflitti",
    },
  });
  card.append(copy, retry);
  return card;
}


function createWorkspaceBlock({ component, eyebrow, title, titleId }) {
  const section = element("section", {
    className: `planning-workspace-block planning-workspace-${component}`,
    attributes: {
      "data-planning-component": component,
      "aria-labelledby": titleId,
    },
  });
  const heading = element("header", { className: "planning-workspace-block-heading" });
  const copy = element("div");
  copy.append(
    element("p", { className: "eyebrow", text: eyebrow }),
    element("h3", { text: title, attributes: { id: titleId } }),
  );
  heading.append(copy);
  const body = element("div", { className: "planning-workspace-block-body" });
  body.append(
    textBlock(`${component}-value`, "planning-workspace-block-value"),
    textBlock(`${component}-detail`, "planning-workspace-description"),
  );
  section.append(heading, body);
  return section;
}


export function createReadinessCard() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-readiness",
    attributes: {
      "data-planning-component": "readiness",
      "aria-labelledby": "planningWorkspaceReadinessTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Verifica" }),
    element("h3", {
      text: "Preparazione del piano",
      attributes: { id: "planningWorkspaceReadinessTitle" },
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-readiness-body",
  });
  const summary = element("div", { className: "planning-readiness-summary" });
  summary.append(
    textBlock("readiness-value", "planning-readiness-score"),
    textBlock("readiness-detail", "planning-workspace-description"),
  );
  const blockers = element("section", {
    className: "planning-readiness-issues critical",
    attributes: {
      "data-planning-role": "readiness-blockers",
      "aria-labelledby": "planningReadinessBlockersTitle",
      hidden: "",
    },
  });
  blockers.append(
    element("h4", {
      text: "Da risolvere",
      attributes: { id: "planningReadinessBlockersTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "readiness-blocker-list" },
    }),
  );
  const warnings = element("section", {
    className: "planning-readiness-issues attention",
    attributes: {
      "data-planning-role": "readiness-warnings",
      "aria-labelledby": "planningReadinessWarningsTitle",
      hidden: "",
    },
  });
  warnings.append(
    element("h4", {
      text: "Da verificare",
      attributes: { id: "planningReadinessWarningsTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "readiness-warning-list" },
    }),
  );
  const metadata = element("dl", {
    className: "planning-readiness-metadata",
    attributes: { "data-planning-role": "readiness-metadata" },
  });
  for (const [label, role, technical = false] of [
    ["Unità operativa", "readiness-unit"],
    ["Data operativa", "readiness-date"],
    ["Ultimo aggiornamento", "readiness-updated", true],
    ["Flusso precedente", "readiness-legacy", true],
  ]) {
    const item = element("div", {
      className: technical ? "planning-technical-detail" : "",
    });
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    metadata.append(item);
  }
  body.append(summary, blockers, warnings, metadata);
  section.append(heading, body);
  return section;
}


export function createConflictSummary() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-conflicts",
    attributes: {
      "data-planning-component": "conflicts",
      "aria-labelledby": "planningWorkspaceConflictsTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Controlli" }),
    element("h3", {
      text: "Riepilogo conflitti",
      attributes: {
        id: "planningWorkspaceConflictsTitle",
        tabindex: "-1",
      },
    }),
    element("p", {
      className: "planning-workspace-description",
      text: "Problemi che richiedono verifica prima della conferma.",
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-conflict-body",
    attributes: {
      "data-planning-role": "conflict-body",
      "aria-live": "polite",
    },
  });
  const summary = element("dl", { className: "planning-conflict-counts" });
  for (const [label, role] of [
    ["Conflitti", "conflict-total"],
    ["Bloccanti", "conflict-blocking"],
    ["Avvisi", "conflict-warnings"],
  ]) {
    const item = element("div");
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    summary.append(item);
  }
  const empty = element("p", {
    className: "planning-conflict-empty",
    text: "Nessun conflitto rilevato.",
    attributes: { "data-planning-role": "conflict-empty" },
  });
  const groups = element("div", {
    className: "planning-conflict-groups",
    attributes: {
      "data-planning-role": "conflict-groups",
      "aria-label": "Gruppi di conflitti",
    },
  });
  const top = element("section", {
    className: "planning-conflict-top",
    attributes: {
      "data-planning-role": "conflict-top",
      "aria-labelledby": "planningConflictTopTitle",
    },
  });
  top.append(
    element("h4", {
      text: "Priorita operative",
      attributes: { id: "planningConflictTopTitle" },
    }),
    element("ol", {
      attributes: { "data-planning-role": "conflict-list" },
    }),
  );
  body.append(summary, empty, groups, top);
  section.append(heading, body);
  return section;
}


export function createPlanningTimeline() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-timeline",
    attributes: {
      "data-planning-component": "timeline",
      "aria-labelledby": "planningWorkspaceTimelineTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Sequenza" }),
    element("h3", {
      text: "Cronologia del piano",
      attributes: { id: "planningWorkspaceTimelineTitle" },
    }),
    element("p", {
      className: "planning-workspace-description",
      text: "Cosa e successo oggi prima che il piano fosse pronto.",
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-timeline-body",
    attributes: {
      "data-planning-role": "timeline-body",
      "aria-live": "polite",
    },
  });
  const summary = element("dl", { className: "planning-timeline-summary" });
  for (const [label, role, technical = false] of [
    ["Eventi", "timeline-count"],
    ["Stato corrente", "timeline-status"],
    ["Ultimo aggiornamento", "timeline-updated", true],
  ]) {
    const item = element("div", {
      className: technical ? "planning-technical-detail" : "",
    });
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    summary.append(item);
  }
  const loading = element("div", {
    className: "planning-timeline-loading",
    attributes: {
      "data-planning-role": "timeline-loading",
      role: "status",
    },
  });
  loading.append(
    element("span", {
      className: "visually-hidden",
      text: "Caricamento cronologia",
    }),
    element("span", { className: "planning-timeline-skeleton" }),
    element("span", { className: "planning-timeline-skeleton" }),
  );
  const empty = element("p", {
    className: "planning-timeline-message",
    text: "Nessun evento disponibile per la giornata.",
    attributes: { "data-planning-role": "timeline-empty", hidden: "" },
  });
  const error = element("div", {
    className: "planning-timeline-error",
    attributes: {
      "data-planning-role": "timeline-error",
      role: "alert",
      hidden: "",
    },
  });
  error.append(
    element("p", {
      attributes: { "data-planning-role": "timeline-error-text" },
    }),
    element("button", {
      className: "secondary",
      text: "Riprova cronologia",
      attributes: {
        type: "button",
        "data-planning-action": "retry-timeline",
      },
    }),
  );
  const groups = element("div", {
    className: "planning-timeline-groups",
    attributes: {
      "data-planning-role": "timeline-groups",
      "aria-label": "Cronologia del piano",
    },
  });
  body.append(summary, loading, empty, error, groups);
  section.append(heading, body);
  return section;
}


export function createPlanningDraft() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-draft",
    attributes: {
      "data-planning-component": "draft",
      "aria-labelledby": "planningWorkspaceDraftTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Proposta" }),
    element("h3", {
      text: "Bozza di pianificazione",
      attributes: { id: "planningWorkspaceDraftTitle" },
    }),
    element("p", {
      className: "planning-workspace-description",
      text: "Proposta modificabile senza effetti sul piano operativo.",
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-draft-body",
    attributes: {
      "data-planning-role": "draft-body",
      "aria-live": "polite",
    },
  });
  const summary = element("dl", {
    className: "planning-draft-summary",
    attributes: { "data-planning-role": "draft-summary", hidden: "" },
  });
  for (const [label, role, technical = false] of [
    ["Nome bozza", "draft-summary-name"],
    ["Stato", "draft-summary-state"],
    ["Versione", "draft-summary-version", true],
    ["Ultima modifica", "draft-summary-updated", true],
  ]) {
    const item = element("div", {
      className: technical ? "planning-technical-detail" : "",
    });
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    summary.append(item);
  }
  const loading = element("div", {
    className: "planning-draft-loading",
    attributes: {
      "data-planning-role": "draft-loading",
      role: "status",
    },
  });
  loading.append(
    element("span", {
      className: "visually-hidden",
      text: "Caricamento bozza di pianificazione",
    }),
    element("span", { className: "planning-draft-skeleton" }),
    element("span", { className: "planning-draft-skeleton short" }),
  );
  const error = element("div", {
    className: "planning-draft-error",
    attributes: {
      "data-planning-role": "draft-error",
      role: "alert",
      hidden: "",
    },
  });
  error.append(
    element("p", { attributes: { "data-planning-role": "draft-error-text" } }),
    element("button", {
      className: "secondary",
      text: "Riprova bozza",
      attributes: {
        type: "button",
        "data-planning-action": "retry-draft",
      },
    }),
  );
  const empty = element("p", {
    className: "planning-draft-empty",
    text: "Nessuna bozza disponibile. Crea una proposta separata dal piano operativo.",
    attributes: { "data-planning-role": "draft-empty", hidden: "" },
  });
  const editor = element("form", {
    className: "planning-draft-editor",
    attributes: {
      "data-planning-role": "draft-editor",
      "aria-label": "Dati della bozza di pianificazione",
    },
  });
  const fields = element("div", { className: "planning-draft-fields" });
  const nameLabel = element("label");
  nameLabel.append(
    element("span", { text: "Nome bozza" }),
    element("input", {
      attributes: {
        type: "text",
        maxlength: "120",
        required: "",
        autocomplete: "off",
        "data-planning-role": "draft-name-input",
      },
    }),
  );
  const noteLabel = element("label");
  noteLabel.append(
    element("span", { text: "Nota" }),
    element("textarea", {
      attributes: {
        rows: "3",
        maxlength: "1000",
        "data-planning-role": "draft-note-input",
      },
    }),
  );
  fields.append(nameLabel, noteLabel);
  const feedback = element("p", {
    className: "planning-draft-feedback",
    attributes: {
      "data-planning-role": "draft-feedback",
      role: "status",
      hidden: "",
    },
  });
  const actions = element("div", {
    className: "planning-draft-actions",
    attributes: { "data-planning-role": "draft-actions" },
  });
  actions.append(
    element("button", {
      text: "Nuova bozza",
      attributes: { type: "button", "data-planning-action": "create-draft" },
    }),
    element("button", {
      text: "Salva",
      attributes: {
        type: "button",
        "data-planning-action": "save-draft",
        hidden: "",
      },
    }),
  );
  const restore = element("div", {
    className: "planning-draft-restore",
    attributes: { "data-planning-role": "draft-restore", hidden: "" },
  });
  const restoreLabel = element("label");
  restoreLabel.append(
    element("span", { text: "Versione da ripristinare" }),
    element("select", {
      attributes: { "data-planning-role": "draft-restore-select" },
    }),
  );
  restore.append(
    restoreLabel,
    element("button", {
      className: "secondary",
      text: "Ripristina",
      attributes: {
        type: "button",
        "data-planning-action": "restore-draft",
      },
    }),
  );
  const deletion = element("div", {
    className: "planning-draft-delete-row",
    attributes: { "data-planning-role": "draft-delete-row", hidden: "" },
  });
  deletion.append(element("button", {
    className: "secondary planning-draft-delete",
    text: "Elimina",
    attributes: { type: "button", "data-planning-action": "delete-draft" },
  }));
  const confirmation = element("div", {
    className: "planning-draft-delete-confirm",
    attributes: {
      "data-planning-role": "draft-delete-confirm",
      role: "group",
      "aria-label": "Conferma eliminazione bozza",
      hidden: "",
    },
  });
  confirmation.append(
    element("p", { text: "Eliminare la bozza dall'area attiva?" }),
    element("button", {
      className: "secondary",
      text: "Annulla",
      attributes: { type: "button", "data-planning-action": "cancel-delete-draft" },
    }),
    element("button", {
      className: "planning-draft-confirm-delete",
      text: "Conferma eliminazione",
      attributes: { type: "button", "data-planning-action": "confirm-delete-draft" },
    }),
  );
  editor.append(fields, feedback, actions, restore, deletion, confirmation);
  const history = element("section", {
    className: "planning-draft-history",
    attributes: {
      "data-planning-role": "draft-history",
      "aria-labelledby": "planningDraftHistoryTitle",
      hidden: "",
    },
  });
  history.append(
    element("h4", {
      text: "Cronologia modifiche",
      attributes: { id: "planningDraftHistoryTitle" },
    }),
    element("ol", { attributes: { "data-planning-role": "draft-history-list" } }),
  );
  body.append(summary, loading, error, empty, editor, history);
  section.append(heading, body);
  return section;
}


export function createPlanningConfirmation() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-confirmation",
    attributes: {
      "data-planning-component": "confirmation",
      "aria-labelledby": "planningWorkspaceConfirmationTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Conferma" }),
    element("h3", {
      text: "Conferma del piano",
      attributes: { id: "planningWorkspaceConfirmationTitle" },
    }),
    element("p", {
      className: "planning-workspace-description",
      text: "Rende immutabile la bozza confermata senza pubblicarla.",
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-confirmation-body",
    attributes: {
      "data-planning-role": "confirmation-body",
      "aria-live": "polite",
      tabindex: "-1",
    },
  });
  const summary = element("dl", {
    className: "planning-confirmation-summary",
    attributes: { "data-planning-role": "confirmation-summary" },
  });
  for (const [label, role, technical = false] of [
    ["Stato", "confirmation-state"],
    ["Bozza", "confirmation-draft"],
    ["Versione", "confirmation-version", true],
    ["Ultimo controllo", "confirmation-updated", true],
  ]) {
    const item = element("div", {
      className: technical ? "planning-technical-detail" : "",
    });
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    summary.append(item);
  }
  const loading = element("div", {
    className: "planning-confirmation-loading",
    attributes: {
      "data-planning-role": "confirmation-loading",
      role: "status",
    },
  });
  loading.append(
    element("span", {
      className: "visually-hidden",
      text: "Caricamento conferma del piano",
    }),
    element("span", { className: "planning-confirmation-skeleton" }),
    element("span", { className: "planning-confirmation-skeleton short" }),
  );
  const error = element("div", {
    className: "planning-confirmation-error",
    attributes: {
      "data-planning-role": "confirmation-error",
      role: "alert",
      hidden: "",
    },
  });
  error.append(
    element("p", {
      attributes: { "data-planning-role": "confirmation-error-text" },
    }),
    element("button", {
      className: "secondary",
      text: "Riprova conferma",
      attributes: {
        type: "button",
        "data-planning-action": "retry-confirmation",
      },
    }),
  );
  const rationale = element("p", {
    className: "planning-confirmation-rationale",
    attributes: { "data-planning-role": "confirmation-rationale" },
  });
  const validation = element("div", {
    className: "planning-confirmation-validation",
    attributes: {
      "data-planning-role": "confirmation-validation",
      "aria-label": "Esito validazione conferma",
    },
  });
  const counts = element("dl", { className: "planning-confirmation-counts" });
  for (const [label, role] of [
    ["Regole superate", "confirmation-passed-count"],
    ["Regole fallite", "confirmation-failed-count"],
  ]) {
    const item = element("div");
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    counts.append(item);
  }
  const passed = element("section", {
    className: "planning-confirmation-rules passed",
    attributes: {
      "data-planning-role": "confirmation-passed",
      "aria-labelledby": "planningConfirmationPassedTitle",
    },
  });
  passed.append(
    element("h4", {
      text: "Verifiche superate",
      attributes: { id: "planningConfirmationPassedTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "confirmation-passed-list" },
    }),
  );
  const failed = element("section", {
    className: "planning-confirmation-rules failed",
    attributes: {
      "data-planning-role": "confirmation-failed",
      "aria-labelledby": "planningConfirmationFailedTitle",
    },
  });
  failed.append(
    element("h4", {
      text: "Da risolvere",
      attributes: { id: "planningConfirmationFailedTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "confirmation-failed-list" },
    }),
  );
  validation.append(counts, failed, passed);
  const feedback = element("p", {
    className: "planning-confirmation-feedback",
    attributes: {
      "data-planning-role": "confirmation-feedback",
      role: "status",
      hidden: "",
    },
  });
  const actions = element("div", {
    className: "planning-confirmation-actions",
    attributes: { "data-planning-role": "confirmation-actions" },
  });
  actions.append(
    element("button", {
      className: "secondary",
      text: "Verifica di nuovo",
      attributes: {
        type: "button",
        "data-planning-action": "validate-confirmation",
      },
    }),
    element("button", {
      text: "Conferma piano",
      attributes: {
        type: "button",
        "data-planning-action": "begin-confirmation",
        "aria-describedby": "planningConfirmationHint",
      },
    }),
  );
  const hint = element("p", {
    className: "planning-confirmation-hint",
    attributes: {
      id: "planningConfirmationHint",
      "data-planning-role": "confirmation-hint",
    },
  });
  const explicit = element("div", {
    className: "planning-confirmation-explicit",
    attributes: {
      "data-planning-role": "confirmation-explicit",
      role: "group",
      "aria-label": "Conferma definitiva della bozza",
      hidden: "",
    },
  });
  explicit.append(
    element("p", {
      text: "La bozza diventerà un piano confermato immutabile. Non verrà pubblicato.",
    }),
    element("button", {
      className: "secondary",
      text: "Annulla",
      attributes: {
        type: "button",
        "data-planning-action": "cancel-confirmation",
      },
    }),
    element("button", {
      text: "Conferma ora",
      attributes: {
        type: "button",
        "data-planning-action": "confirm-now",
      },
    }),
  );
  const history = element("section", {
    className: "planning-confirmation-history",
    attributes: {
      "data-planning-role": "confirmation-history",
      "aria-labelledby": "planningConfirmationHistoryTitle",
      hidden: "",
    },
  });
  history.append(
    element("h4", {
      text: "Cronologia conferme",
      attributes: { id: "planningConfirmationHistoryTitle" },
    }),
    element("ol", {
      attributes: { "data-planning-role": "confirmation-history-list" },
    }),
  );
  body.append(
    summary,
    loading,
    error,
    rationale,
    validation,
    feedback,
    actions,
    hint,
    explicit,
    history,
  );
  section.append(heading, body);
  return section;
}


export function createPlanningPublication() {
  const section = element("section", {
    className: "planning-workspace-block planning-workspace-publication",
    attributes: {
      "data-planning-component": "publication",
      "aria-labelledby": "planningWorkspacePublicationTitle",
    },
  });
  const heading = element("header", {
    className: "planning-workspace-block-heading",
  });
  heading.append(
    element("p", { className: "eyebrow", text: "Pubblicazione" }),
    element("h3", {
      text: "Pubblicazione del piano",
      attributes: { id: "planningWorkspacePublicationTitle" },
    }),
    element("p", {
      className: "planning-workspace-description",
      text: "Rende disponibile il piano confermato senza avviare l'esecuzione.",
    }),
  );
  const body = element("div", {
    className: "planning-workspace-block-body planning-publication-body",
    attributes: {
      "data-planning-role": "publication-body",
      "aria-live": "polite",
      tabindex: "-1",
    },
  });
  const summary = element("dl", {
    className: "planning-publication-summary",
    attributes: { "data-planning-role": "publication-summary" },
  });
  for (const [label, role, technical = false] of [
    ["Stato", "publication-state"],
    ["Versione", "publication-version", true],
    ["Pubblicato", "publication-updated", true],
    ["Responsabile", "publication-actor", true],
    ["Piano confermato", "publication-confirmation", true],
    ["Fingerprint", "publication-fingerprint", true],
  ]) {
    const item = element("div", {
      className: technical ? "planning-technical-detail" : "",
    });
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    summary.append(item);
  }
  const loading = element("div", {
    className: "planning-publication-loading",
    attributes: {
      "data-planning-role": "publication-loading",
      role: "status",
    },
  });
  loading.append(
    element("span", {
      className: "visually-hidden",
      text: "Caricamento pubblicazione del piano",
    }),
    element("span", { className: "planning-publication-skeleton" }),
    element("span", { className: "planning-publication-skeleton short" }),
  );
  const error = element("div", {
    className: "planning-publication-error",
    attributes: {
      "data-planning-role": "publication-error",
      role: "alert",
      hidden: "",
    },
  });
  error.append(
    element("p", {
      attributes: { "data-planning-role": "publication-error-text" },
    }),
    element("button", {
      className: "secondary",
      text: "Riprova pubblicazione",
      attributes: {
        type: "button",
        "data-planning-action": "retry-publication",
      },
    }),
  );
  const rationale = element("p", {
    className: "planning-publication-rationale",
    attributes: { "data-planning-role": "publication-rationale" },
  });
  const validation = element("div", {
    className: "planning-publication-validation",
    attributes: {
      "data-planning-role": "publication-validation",
      "aria-label": "Esito validazione pubblicazione",
    },
  });
  const counts = element("dl", { className: "planning-publication-counts" });
  for (const [label, role] of [
    ["Regole superate", "publication-passed-count"],
    ["Regole fallite", "publication-failed-count"],
  ]) {
    const item = element("div");
    item.append(
      element("dt", { text: label }),
      element("dd", { attributes: { "data-planning-role": role } }),
    );
    counts.append(item);
  }
  const passed = element("section", {
    className: "planning-publication-rules passed",
    attributes: {
      "data-planning-role": "publication-passed",
      "aria-labelledby": "planningPublicationPassedTitle",
    },
  });
  passed.append(
    element("h4", {
      text: "Verifiche superate",
      attributes: { id: "planningPublicationPassedTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "publication-passed-list" },
    }),
  );
  const failed = element("section", {
    className: "planning-publication-rules failed",
    attributes: {
      "data-planning-role": "publication-failed",
      "aria-labelledby": "planningPublicationFailedTitle",
    },
  });
  failed.append(
    element("h4", {
      text: "Da risolvere",
      attributes: { id: "planningPublicationFailedTitle" },
    }),
    element("ul", {
      attributes: { "data-planning-role": "publication-failed-list" },
    }),
  );
  validation.append(counts, failed, passed);
  const feedback = element("p", {
    className: "planning-publication-feedback",
    attributes: {
      "data-planning-role": "publication-feedback",
      role: "status",
      hidden: "",
    },
  });
  const actions = element("div", {
    className: "planning-publication-actions",
    attributes: { "data-planning-role": "publication-actions" },
  });
  actions.append(
    element("button", {
      className: "secondary",
      text: "Verifica di nuovo",
      attributes: {
        type: "button",
        "data-planning-action": "validate-publication",
      },
    }),
    element("button", {
      text: "Pubblica piano",
      attributes: {
        type: "button",
        "data-planning-action": "begin-publication",
        "aria-describedby": "planningPublicationHint",
      },
    }),
  );
  const hint = element("p", {
    className: "planning-publication-hint",
    attributes: {
      id: "planningPublicationHint",
      "data-planning-role": "publication-hint",
    },
  });
  const explicit = element("div", {
    className: "planning-publication-explicit",
    attributes: {
      "data-planning-role": "publication-explicit",
      role: "group",
      "aria-label": "Pubblicazione esplicita del piano confermato",
      hidden: "",
    },
  });
  explicit.append(
    element("p", {
      text: "Il piano confermato diventerà disponibile agli altri workspace. Nessuna esecuzione verrà avviata.",
    }),
    element("button", {
      className: "secondary",
      text: "Annulla",
      attributes: {
        type: "button",
        "data-planning-action": "cancel-publication",
      },
    }),
    element("button", {
      text: "Pubblica ora",
      attributes: {
        type: "button",
        "data-planning-action": "publish-now",
      },
    }),
  );
  const history = element("section", {
    className: "planning-publication-history",
    attributes: {
      "data-planning-role": "publication-history",
      "aria-labelledby": "planningPublicationHistoryTitle",
      hidden: "",
    },
  });
  history.append(
    element("h4", {
      text: "Cronologia pubblicazioni",
      attributes: { id: "planningPublicationHistoryTitle" },
    }),
    element("ol", {
      attributes: { "data-planning-role": "publication-history-list" },
    }),
  );
  body.append(
    summary,
    loading,
    error,
    rationale,
    validation,
    feedback,
    actions,
    hint,
    explicit,
    history,
  );
  section.append(heading, body);
  return section;
}


export function createFooterActions() {
  const footer = element("footer", {
    className: "planning-workspace-footer",
    attributes: {
      "data-planning-component": "actions",
      "aria-label": "Azioni del Planning operativo",
    },
  });
  const copy = element("div");
  copy.append(
    element("strong", { text: "Azioni" }),
    element("p", {
      text: "Il Planning legacy resta l'unica fonte operativa.",
    }),
  );
  const actions = element("div", {
    className: "planning-workspace-actions",
    attributes: { "data-planning-role": "actions" },
  });
  actions.append(
    element("button", {
      className: "secondary",
      text: "Apri flusso legacy",
      attributes: {
        type: "button",
        "data-planning-action": "open-legacy",
        "aria-controls": "legacyOperationsRegion",
        "aria-expanded": "false",
      },
    }),
  );
  footer.append(copy, actions);
  return footer;
}


export function createPlanningLoadingState() {
  const loading = element("div", {
    className: "planning-workspace-loading",
    attributes: {
      "data-planning-role": "loading",
      role: "status",
    },
  });
  loading.append(
    element("span", {
      className: "visually-hidden",
      text: "Caricamento Planning operativo",
    }),
    element("span", { className: "planning-workspace-skeleton" }),
    element("span", { className: "planning-workspace-skeleton" }),
    element("span", { className: "planning-workspace-skeleton" }),
  );
  return loading;
}

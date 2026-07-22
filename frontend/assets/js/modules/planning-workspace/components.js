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
      text: "Planning Workspace",
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
    element("dt", { text: "Operational Unit" }),
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
  card.append(copy);
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
  return createWorkspaceBlock({
    component: "readiness",
    eyebrow: "Verifica",
    title: "Planning Readiness",
    titleId: "planningWorkspaceReadinessTitle",
  });
}


export function createConflictSummary() {
  return createWorkspaceBlock({
    component: "conflicts",
    eyebrow: "Controlli",
    title: "Conflict Summary",
    titleId: "planningWorkspaceConflictsTitle",
  });
}


export function createTimelinePlaceholder() {
  return createWorkspaceBlock({
    component: "timeline",
    eyebrow: "Sequenza",
    title: "Planning Timeline",
    titleId: "planningWorkspaceTimelineTitle",
  });
}


export function createDraftPlaceholder() {
  return createWorkspaceBlock({
    component: "draft",
    eyebrow: "Proposta",
    title: "Planning Draft",
    titleId: "planningWorkspaceDraftTitle",
  });
}


export function createPublicationPlaceholder() {
  return createWorkspaceBlock({
    component: "publication",
    eyebrow: "Ciclo di vita",
    title: "Publication Status",
    titleId: "planningWorkspacePublicationTitle",
  });
}


export function createFooterActions() {
  const footer = element("footer", {
    className: "planning-workspace-footer",
    attributes: {
      "data-planning-component": "actions",
      "aria-label": "Azioni Planning Workspace",
    },
  });
  const copy = element("div");
  copy.append(
    element("strong", { text: "Azioni" }),
    element("p", {
      text: "La conferma sarà disponibile quando i contratti saranno collegati.",
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
    element("button", {
      text: "Conferma piano",
      attributes: {
        type: "button",
        "data-planning-action": "confirm",
        disabled: "",
        "aria-describedby": "planningWorkspaceActionHint",
      },
    }),
  );
  const hint = element("span", {
    className: "visually-hidden",
    text: "Planning Runtime non ancora collegato",
    attributes: { id: "planningWorkspaceActionHint" },
  });
  footer.append(copy, actions, hint);
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
      text: "Caricamento Planning Workspace",
    }),
    element("span", { className: "planning-workspace-skeleton" }),
    element("span", { className: "planning-workspace-skeleton" }),
    element("span", { className: "planning-workspace-skeleton" }),
  );
  return loading;
}

import {
  generateDailyBriefing,
  getLatestDailyBriefing,
} from "../api.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import {
  applyBriefingEvent,
  createBriefingState,
  deriveBriefingView,
} from "./briefing-state.js";


let briefingState = createBriefingState();
let briefingRequestId = 0;


const ATTENTION_LABELS = {
  stable: "Stabile",
  attention: "Attenzione",
  critical: "Critico",
  unavailable: "Non disponibile",
};

const READINESS_LABELS = {
  green: "Pronta (green)",
  yellow: "Attenzione (yellow)",
  red: "Critica (red)",
};

const SEVERITY_LABELS = {
  blocker: "Bloccante",
  critical: "Critico",
  high: "Alta",
  medium: "Media",
  low: "Bassa",
  information: "Informazione",
};

const PROVENANCE_LABELS = {
  observed: "Fatto osservato",
  configured: "Dato configurato",
  derived: "Dato derivato",
  suggestion: "Suggerimento",
  limitation: "Limite",
};


function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}


function localizedTimestamp(value) {
  if (!value) return "Non disponibile";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT");
}


function showBriefingSurface(surface) {
  byId("briefingViewState").hidden = surface !== "state";
  byId("briefingDataView").hidden = surface !== "data";
}


function renderLoading() {
  showBriefingSurface("state");
  const state = byId("briefingViewState");
  state.className = "briefing-view-state loading";
  state.setAttribute("aria-busy", "true");
  byId("briefingLoading").hidden = false;
  byId("briefingStateContent").hidden = true;
}


function renderState(view) {
  showBriefingSurface("state");
  byId("briefingIssueList").replaceChildren();
  const state = byId("briefingViewState");
  state.className = `briefing-view-state ${view.error ? "error" : "empty"}`;
  state.setAttribute("aria-busy", "false");
  byId("briefingLoading").hidden = true;
  byId("briefingStateContent").hidden = false;
  byId("briefingStateTitle").textContent = view.error
    ? "Briefing temporaneamente non disponibile"
    : "Nessun briefing disponibile";
  byId("briefingStateDescription").textContent = view.error
    ? view.errorMessage
    : view.emptyMessage;
  byId("briefingStateActions").hidden = view.error;
  byId("briefingDemoBtn").hidden = !view.showDemoAction;
}


function setSnapshotField(id, value) {
  byId(id).textContent = value ?? "Non disponibile";
}


function renderSummary(briefing) {
  const level = briefing.attention_level;
  const badge = byId("briefingAttentionBadge");
  badge.className = `briefing-attention-badge ${level}`;
  badge.textContent = ATTENTION_LABELS[level] || level;
  byId("briefingExecutiveSummary").textContent = briefing.executive_summary;
  byId("briefingAttentionReason").textContent = briefing.attention_reason;
  byId("briefingMetadata").textContent = (
    `Planning ${briefing.planning_id} · versione `
    + `${briefing.planning_version} · ${briefing.operation_date} · `
    + `generato ${localizedTimestamp(briefing.generated_at)}`
  );
  byId("briefingDemoBadge").hidden = !briefing.is_demo;

  const readiness = briefing.readiness_snapshot;
  setSnapshotField(
    "briefingReadinessLevel",
    readiness.available
      ? READINESS_LABELS[readiness.level] || readiness.level
      : "Non disponibile",
  );
  setSnapshotField(
    "briefingReadinessIssues",
    readiness.available
      ? `${readiness.blocking_issues} bloccanti · ${readiness.warnings} warning`
      : readiness.reasons[0],
  );

  const capacity = briefing.capacity_snapshot;
  setSnapshotField(
    "briefingCapacityMargin",
    capacity.available ? capacity.margin : "Non disponibile",
  );
  setSnapshotField(
    "briefingCapacityDetail",
    capacity.available
      ? `Domanda ${capacity.demand} · capacità ${capacity.available_capacity} · soglia ${capacity.reserve_threshold}`
      : "Snapshot Capacity non disponibile",
  );

  setSnapshotField(
    "briefingCriticalCount",
    briefing.metrics.critical_items,
  );
  setSnapshotField(
    "briefingAttentionCount",
    briefing.metrics.attention_items,
  );
  setSnapshotField(
    "briefingInformationCount",
    briefing.metrics.information_items,
  );
  setSnapshotField(
    "briefingActionCount",
    briefing.metrics.recommended_actions,
  );
}


function renderFacts(facts) {
  const list = element("dl", "briefing-facts");
  facts.forEach((fact) => {
    const row = element("div", "briefing-fact");
    const term = element("dt", "", fact.label);
    const value = typeof fact.value === "object"
      ? JSON.stringify(fact.value)
      : String(fact.value);
    const definition = element("dd", "", value);
    const provenance = element(
      "span",
      `briefing-provenance ${fact.provenance}`,
      PROVENANCE_LABELS[fact.provenance] || fact.provenance,
    );
    definition.append(provenance);
    row.append(term, definition);
    list.append(row);
  });
  return list;
}


function renderSources(references) {
  const details = element("details", "briefing-sources");
  const summary = element(
    "summary",
    "",
    `Fonti verificate (${references.length})`,
  );
  const list = element("ul");
  references.forEach((reference) => {
    list.append(element(
      "li",
      "",
      `${reference.label}: ${reference.source_type} `
      + `${reference.source_id} · ${reference.field_path}`,
    ));
  });
  details.append(summary, list);
  return details;
}


function renderActionLink(link) {
  const button = element("button", "briefing-action-link", link.label);
  button.type = "button";
  button.dataset.briefingWorkspace = link.workspace;
  button.dataset.briefingTarget = link.target_id;
  if (link.entity_type) button.dataset.entityType = link.entity_type;
  if (link.entity_id) button.dataset.entityId = link.entity_id;
  return button;
}


function renderSection(section) {
  const card = element(
    "article",
    `briefing-issue-card severity-${section.severity}`,
  );
  card.dataset.priority = String(section.priority);
  card.dataset.severity = section.severity;
  const header = element("header", "briefing-issue-header");
  const heading = element("div");
  heading.append(
    element("span", "briefing-priority", `Priorità ${section.priority}`),
    element("h3", "", section.title),
  );
  const badge = element(
    "span",
    `briefing-severity ${section.severity}`,
    SEVERITY_LABELS[section.severity] || section.severity,
  );
  header.append(heading, badge);
  card.append(
    header,
    element("p", "briefing-issue-summary", section.summary),
  );
  if (section.facts.length) card.append(renderFacts(section.facts));

  const rationale = element("div", "briefing-rationale");
  rationale.append(
    element("strong", "", "Perché conta"),
    element("p", "", section.rationale),
  );
  card.append(rationale);

  if (section.recommendation) {
    const recommendation = element("div", "briefing-recommendation");
    recommendation.append(
      element("strong", "", "Azione consigliata"),
      element("p", "", section.recommendation.text),
      element(
        "small",
        "",
        "Richiede conferma umana. Nessuna modifica automatica.",
      ),
    );
    card.append(recommendation);
  }

  const footer = element("footer", "briefing-issue-footer");
  section.action_links.forEach((link) => {
    footer.append(renderActionLink(link));
  });
  footer.append(renderSources(section.source_references));
  card.append(
    element(
      "p",
      "briefing-ranking",
      section.ranking_explanation,
    ),
    footer,
  );
  return card;
}


function renderSections(view) {
  const list = byId("briefingIssueList");
  list.replaceChildren();
  if (!view.sections.length) {
    list.append(element(
      "div",
      "empty-state",
      "Nessun elemento per il filtro selezionato.",
    ));
    return;
  }
  view.sections.forEach((section) => {
    list.append(renderSection(section));
  });
}


function renderAvailable(view) {
  showBriefingSurface("data");
  renderSummary(view.briefing);
  document.querySelectorAll("[data-briefing-filter]").forEach((button) => {
    const active = button.dataset.briefingFilter === view.selectedFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderSections(view);
}


function renderBriefing() {
  const view = deriveBriefingView(briefingState);
  if (view.loading) {
    renderLoading();
  } else if (view.available) {
    renderAvailable(view);
  } else {
    renderState(view);
  }
}


function updateBriefing(event) {
  briefingState = applyBriefingEvent(briefingState, event);
  renderBriefing();
}


async function fetchBriefing({ generate = false } = {}) {
  const requestId = ++briefingRequestId;
  updateBriefing({ type: "load-started" });
  try {
    let response = await getLatestDailyBriefing();
    if (generate || (
      response.status === "unavailable" && response.planning_id
    )) {
      response = await generateDailyBriefing(
        response.planning_id || null,
      );
    }
    if (requestId === briefingRequestId) {
      updateBriefing({ type: "load-completed", briefing: response });
    }
  } catch (error) {
    const presentation = userErrorPresentation(
      "briefing.load",
      error,
      {
        statuses: [400, 409, 422],
        fallback: "Non è stato possibile caricare il briefing.",
      },
    );
    if (requestId === briefingRequestId) {
      updateBriefing({
        type: "load-failed",
        message: presentation.message,
      });
    }
  }
}


async function refreshBriefing() {
  const button = byId("refreshBriefingBtn");
  setLoading(button, true, "Aggiornamento...");
  try {
    await fetchBriefing({ generate: true });
    setMessage("Briefing operativo aggiornato.", "success");
  } finally {
    setLoading(button, false);
  }
}


function handleBriefingClick(event) {
  const filter = event.target.closest("[data-briefing-filter]");
  if (filter) {
    updateBriefing({
      type: "filter-selected",
      filter: filter.dataset.briefingFilter,
    });
    return;
  }
  const action = event.target.closest("[data-briefing-workspace]");
  if (action) {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: {
        view: action.dataset.briefingWorkspace,
        targetId: action.dataset.briefingTarget,
        entityType: action.dataset.entityType || null,
        entityId: action.dataset.entityId || null,
      },
    }));
  }
}


export function initBriefing() {
  byId("briefingSection").addEventListener("click", handleBriefingClick);
  byId("refreshBriefingBtn").addEventListener("click", refreshBriefing);
  byId("briefingImportBtn").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "operations", targetId: "importsSection" },
    }));
  });
  byId("briefingDemoBtn").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("demo:load-requested"));
  });
  document.addEventListener("demo:availability-changed", (event) => {
    updateBriefing({
      type: "demo-availability",
      enabled: event.detail.enabled,
    });
  });
  document.addEventListener("demo:workspace-changed", (event) => {
    if (event.detail.status === "ready") {
      fetchBriefing({ generate: true });
    }
    if (event.detail.status === "reset") {
      fetchBriefing();
    }
  });
  document.addEventListener("planning:availability-changed", (event) => {
    fetchBriefing({ generate: event.detail.hasPlanning });
  });
  renderBriefing();
  fetchBriefing();
}

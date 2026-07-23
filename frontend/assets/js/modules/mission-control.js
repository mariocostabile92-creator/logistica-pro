import { byId } from "../utils/dom.js";
import { scheduleIdle } from "../utils/idle-scheduler.js";
import { userFacingCopy } from "./briefing.js";
import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "./mission-control-state.js";


let missionState = createMissionControlState();
let clockTimer = null;
let refreshPromise = null;
let cancelTimelineRender = null;
let renderVersion = 0;
let initialized = false;
let refreshData = async () => [];
let changeOperationalUnit = () => {};
const renderSignatures = new Map();


function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}


function validDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}


function shortTimestamp(value) {
  const date = validDate(value);
  if (!date) return "Non disponibile";
  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}


function relativeFreshness(value) {
  const date = validDate(value);
  if (!date) return "Aggiornamento non disponibile";
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (elapsedMinutes < 1) return "Aggiornato adesso";
  if (elapsedMinutes === 1) return "Aggiornato 1 min fa";
  if (elapsedMinutes < 60) return `Aggiornato ${elapsedMinutes} min fa`;
  return `Aggiornato ${shortTimestamp(value)}`;
}


function setText(id, value) {
  const node = byId(id);
  if (node.textContent !== String(value)) node.textContent = value;
}


function renderChanged(key, value, callback) {
  const signature = JSON.stringify(value);
  if (renderSignatures.get(key) === signature) return false;
  renderSignatures.set(key, signature);
  callback();
  return true;
}


function updateClock() {
  const now = new Date();
  setText("missionDate", now.toLocaleDateString("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }));
  setText("missionTime", now.toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
  }));
  setText(
    "missionFreshness",
    relativeFreshness(deriveMissionControlView(missionState).freshnessAt),
  );
}


function renderStatus(view) {
  const signature = {
    status: view.status,
    loading: view.loading,
    refreshing: view.refreshing,
    workforce: view.workforce.availabilityLabel,
    fleet: view.fleet.availableLabel,
    blocking: view.planning.blocking,
  };
  renderChanged("status", signature, () => {
    const status = byId("missionDayStatus");
    status.className = `mission-day-status is-${view.status.tone}`;
    status.setAttribute("aria-busy", String(view.loading || view.refreshing));
    setText("missionDayStatusLabel", view.status.label);
    setText("missionDayStatusDescription", userFacingCopy(view.status.description));
    byId("missionStatusTemporary").hidden = !view.status.temporary;
    setText("missionWorkforceKpi", view.workforce.availabilityLabel);
    setText("missionFleetKpi", view.fleet.availableLabel);
    setText(
      "missionConflictKpi",
      view.planning.blocking === null ? "Dato non esposto" : view.planning.blocking,
    );
  });
}


function actionButton(action) {
  if (!action.workspace || !action.actionLabel) return null;
  const button = element("button", "", action.actionLabel);
  button.type = "button";
  button.dataset.missionWorkspace = action.workspace;
  if (action.targetId) button.dataset.missionTarget = action.targetId;
  if (action.entityType) button.dataset.entityType = action.entityType;
  if (action.entityId) button.dataset.entityId = action.entityId;
  return button;
}


function actionRow(action) {
  const row = element("article", "mission-action-row");
  row.dataset.missionAction = action.id;
  const copy = element("div", "mission-action-copy");
  const meta = element("div", "mission-action-meta");
  meta.append(
    element(
      "span",
      `mission-action-priority is-${action.tone}`,
      action.priority
        ? `${action.priorityLabel} \u00b7 priorit\u00e0 ${action.priority}`
        : action.priorityLabel,
    ),
    element("span", "mission-action-source", action.sourceLabel),
  );
  copy.append(
    meta,
    element("h4", "", userFacingCopy(action.title)),
    element("p", "", userFacingCopy(action.summary)),
  );
  row.append(copy);
  const button = actionButton(action);
  if (button) row.append(button);
  return row;
}


function renderActions(view) {
  const signature = {
    state: view.actionState,
    actions: view.actions,
    error: view.error,
    title: view.actionEmptyTitle,
    description: view.actionEmptyDescription,
  };
  renderChanged("actions", signature, () => {
    const state = byId("missionActionsState");
    const list = byId("missionActionsList");
    setText(
      "missionActionCount",
      view.actionState === "loading" ? "--" : view.actions.length,
    );
    if (view.actionState === "loading") {
      state.hidden = false;
      state.className = "mission-actions-state is-loading";
      state.setAttribute("aria-busy", "true");
      list.hidden = true;
      return;
    }
    state.setAttribute("aria-busy", "false");
    if (view.actionState === "empty") {
      state.hidden = false;
      state.className = `mission-actions-state ${view.error ? "is-error" : "is-empty"}`;
      state.replaceChildren(
        element("strong", "", view.actionEmptyTitle),
        element("p", "", view.actionEmptyDescription),
      );
      list.hidden = true;
      return;
    }
    state.hidden = true;
    list.hidden = false;
    list.replaceChildren(...view.actions.map(actionRow));
  });
}


function renderModuleState(id, state) {
  const badge = byId(id);
  setText(id, state.label);
  badge.className = `mission-module-state is-${state.tone}`;
}


function renderSnapshots(view) {
  renderChanged("snapshots", {
    workforce: view.workforce,
    fleet: view.fleet,
    planning: view.planning,
  }, () => {
    renderModuleState("missionWorkforceState", view.workforce.state);
    setText("missionWorkforceAvailability", view.workforce.availabilityLabel);
    setText("missionWorkforceAbsences", view.workforce.absencesLabel);
    renderModuleState("missionFleetState", view.fleet.state);
    setText("missionFleetAvailable", view.fleet.availableLabel);
    setText("missionFleetMaintenance", view.fleet.maintenanceLabel);
    setText("missionFleetDocuments", view.fleet.documentsLabel);
    renderModuleState("missionPlanningState", view.planning.state);
    setText("missionPlanningReadiness", view.planning.readiness);
    setText("missionPlanningConflicts", view.planning.conflictsLabel);
    setText(
      "missionPlanningGenerated",
      view.planning.generatedAt ? shortTimestamp(view.planning.generatedAt) : "Non registrata",
    );
  });
}


function renderOperationalUnits(view) {
  renderChanged("operational-units", view.operationalUnits, () => {
    const select = byId("missionOperationalUnit");
    select.replaceChildren(...view.operationalUnits.options.map((option) => {
      const node = element("option", "", option.label);
      node.value = option.value;
      return node;
    }));
    select.value = view.operationalUnits.selected;
    select.disabled = view.operationalUnits.disabled;
    const unitCount = Math.max(0, view.operationalUnits.options.length - 1);
    setText(
      "missionOperationalUnitHint",
      unitCount
        ? `${unitCount} unit\u00e0 nei dati \u00b7 filtro temporaneo`
        : "Selettore predisposto \u00b7 dati aggregati",
    );
  });
}


function renderTimeline(view) {
  renderChanged("timeline", view.timeline, () => {
    const list = byId("missionTimelineList");
    if (!view.timeline.length) {
      list.replaceChildren(element(
        "li",
        "mission-timeline-placeholder",
        "Nessuna attivit\u00e0 disponibile nei dati correnti.",
      ));
      return;
    }
    list.replaceChildren(...view.timeline.map((item) => {
      const row = element("li", "mission-timeline-item");
      const time = element("time", "", shortTimestamp(item.timestamp));
      time.dateTime = item.timestamp;
      row.append(time, element("strong", "", item.label), element("span", "", item.source));
      return row;
    }));
  });
}


function renderControls(view) {
  setText(
    "missionFreshness",
    view.refreshError
      ? "Aggiornamento incompleto \u00b7 dati precedenti"
      : relativeFreshness(view.freshnessAt),
  );
  const refresh = byId("missionRefreshBtn");
  refresh.disabled = view.loading || view.refreshing;
  setText("missionRefreshBtn", view.refreshing ? "Aggiornamento..." : "Aggiorna");
}


function renderMissionControl({ initial = false } = {}) {
  const view = deriveMissionControlView(missionState);
  renderStatus(view);
  renderControls(view);
  if (initial) return;
  const version = ++renderVersion;
  queueMicrotask(() => {
    if (version === renderVersion) renderActions(view);
  });
  requestAnimationFrame(() => {
    if (version !== renderVersion) return;
    renderSnapshots(view);
    renderOperationalUnits(view);
  });
  cancelTimelineRender?.();
  cancelTimelineRender = scheduleIdle(() => {
    cancelTimelineRender = null;
    if (version === renderVersion) renderTimeline(view);
  });
}


function updateMissionControl(event) {
  missionState = applyMissionControlEvent(missionState, event);
  renderMissionControl();
}


function handleWorkspaceNavigation(event) {
  const button = event.target.closest("[data-mission-workspace]");
  if (!button) return;
  document.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: {
      view: button.dataset.missionWorkspace,
      targetId: button.dataset.missionTarget || null,
      entityType: button.dataset.entityType || null,
      entityId: button.dataset.entityId || null,
    },
  }));
}


async function handleRefresh() {
  if (refreshPromise) return refreshPromise;
  updateMissionControl({ type: "refresh-started" });
  refreshPromise = Promise.resolve(refreshData())
    .then((results) => {
      const partialFailure = Array.isArray(results) && results.some((result) => (
        result.status === "rejected" || result.value === null
      ));
      updateMissionControl({
        type: "refresh-settled",
        error: partialFailure ? "Uno snapshot non \u00e8 stato aggiornato." : "",
      });
    })
    .catch(() => {
      updateMissionControl({
        type: "refresh-settled",
        error: "Aggiornamento temporaneamente non disponibile.",
      });
    })
    .finally(() => { refreshPromise = null; });
  return refreshPromise;
}


function handleOperationalUnitChange(event) {
  const operationalUnit = event.target.value;
  if (operationalUnit === missionState.selectedOperationalUnit) return;
  changeOperationalUnit(operationalUnit);
  updateMissionControl({ type: "operational-unit-selected", operationalUnit });
  document.dispatchEvent(new CustomEvent("mission:operational-unit-changed", {
    detail: { operationalUnit },
  }));
}


export function initMissionControl({
  onRefresh = null,
  onOperationalUnitChange = null,
} = {}) {
  if (initialized) return;
  initialized = true;
  if (onRefresh) refreshData = onRefresh;
  if (onOperationalUnitChange) changeOperationalUnit = onOperationalUnitChange;
  updateClock();
  clockTimer = window.setInterval(updateClock, 60000);
  byId("missionControlSection").addEventListener("click", handleWorkspaceNavigation);
  byId("missionRefreshBtn").addEventListener("click", handleRefresh);
  byId("missionOperationalUnit").addEventListener("change", handleOperationalUnitChange);
  document.addEventListener("briefing:state-changed", (event) => {
    if (event.detail.phase === "loading") {
      updateMissionControl({ type: "briefing-loading" });
    } else if (event.detail.phase === "error") {
      updateMissionControl({
        type: "briefing-failed",
        message: event.detail.errorMessage,
      });
    }
  });
  document.addEventListener("briefing:changed", (event) => {
    updateMissionControl({ type: "briefing-loaded", briefing: event.detail.briefing });
  });
  document.addEventListener("workspace:status-changed", (event) => {
    updateMissionControl({ type: "workspace-loaded", workspace: event.detail });
  });
  document.addEventListener("workspace:reset-completed", () => {
    updateMissionControl({
      type: "workspace-reset",
      workspace: {
        workspace_state: "EMPTY",
        workforce_member_count: 0,
        asset_count: 0,
        planning_count: 0,
      },
    });
  });
  window.addEventListener("beforeunload", () => {
    if (clockTimer) window.clearInterval(clockTimer);
    cancelTimelineRender?.();
  });
  renderMissionControl({ initial: true });
}

import { byId } from "../utils/dom.js";
import { userFacingCopy } from "./briefing.js";
import {
  applyMissionControlEvent,
  createMissionControlState,
  deriveMissionControlView,
} from "./mission-control-state.js";


let missionState = createMissionControlState();
let clockTimer = null;


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


function updateClock() {
  const now = new Date();
  byId("missionDate").textContent = now.toLocaleDateString("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  byId("missionTime").textContent = now.toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
  });
}


function renderStatus(view) {
  const status = byId("missionDayStatus");
  status.className = `mission-day-status is-${view.status.tone}`;
  status.setAttribute("aria-busy", String(view.loading || view.refreshing));
  byId("missionDayStatusLabel").textContent = view.status.label;
  byId("missionDayStatusDescription").textContent = userFacingCopy(
    view.status.description,
  );
  byId("missionStatusTemporary").hidden = !view.status.temporary;
  byId("missionWorkforceKpi").textContent = view.workforce.availabilityLabel;
  byId("missionFleetKpi").textContent = view.fleet.availableLabel;
  byId("missionConflictKpi").textContent = view.planning.blocking === null
    ? "Non disponibile"
    : String(view.planning.blocking);
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
      action.priority ? `${action.priorityLabel} · priorità ${action.priority}` : action.priorityLabel,
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
  const state = byId("missionActionsState");
  const list = byId("missionActionsList");
  byId("missionActionCount").textContent = view.actionState === "loading"
    ? "--"
    : String(view.actions.length);
  if (view.actionState === "loading") {
    state.hidden = false;
    state.className = "mission-actions-state is-loading";
    state.setAttribute("aria-busy", "true");
    state.replaceChildren();
    const skeleton = element("div", "mission-actions-skeleton");
    skeleton.setAttribute("aria-hidden", "true");
    skeleton.append(element("span"), element("span"), element("span"));
    state.append(skeleton);
    list.hidden = true;
    list.replaceChildren();
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
    list.replaceChildren();
    return;
  }
  state.hidden = true;
  list.hidden = false;
  list.replaceChildren(...view.actions.map(actionRow));
}


function renderModuleState(id, state) {
  const badge = byId(id);
  badge.textContent = state.label;
  badge.className = `mission-module-state is-${state.tone}`;
}


function renderSnapshots(view) {
  renderModuleState("missionWorkforceState", view.workforce.state);
  byId("missionWorkforceAvailability").textContent = view.workforce.availabilityLabel;
  byId("missionWorkforceAbsences").textContent = view.workforce.absencesLabel;

  renderModuleState("missionFleetState", view.fleet.state);
  byId("missionFleetAvailable").textContent = view.fleet.availableLabel;
  byId("missionFleetMaintenance").textContent = view.fleet.maintenanceLabel;
  byId("missionFleetDocuments").textContent = view.fleet.documentsLabel;

  renderModuleState("missionPlanningState", view.planning.state);
  byId("missionPlanningReadiness").textContent = view.planning.readiness;
  byId("missionPlanningConflicts").textContent = view.planning.conflictsLabel;
  byId("missionPlanningGenerated").textContent = view.planning.generatedAt
    ? shortTimestamp(view.planning.generatedAt)
    : "Non disponibile";
}


function renderOperationalUnits(view) {
  const select = byId("missionOperationalUnit");
  select.replaceChildren(...view.operationalUnits.options.map((option) => {
    const node = element("option", "", option.label);
    node.value = option.value;
    return node;
  }));
  select.value = view.operationalUnits.selected;
  select.disabled = view.operationalUnits.disabled;
  const unitCount = Math.max(0, view.operationalUnits.options.length - 1);
  byId("missionOperationalUnitHint").textContent = unitCount
    ? `${unitCount} unità nello snapshot · filtro temporaneo`
    : "Selettore predisposto · snapshot aggregato";
}


function renderTimeline(view) {
  const list = byId("missionTimelineList");
  if (!view.timeline.length) {
    list.replaceChildren(element(
      "li",
      "mission-timeline-placeholder",
      "Nessuna attività disponibile nello snapshot corrente.",
    ));
    return;
  }
  list.replaceChildren(...view.timeline.map((item) => {
    const row = element("li", "mission-timeline-item");
    const time = element("time", "", shortTimestamp(item.timestamp));
    time.dateTime = item.timestamp;
    row.append(
      time,
      element("strong", "", item.label),
      element("span", "", item.source),
    );
    return row;
  }));
}


function renderMissionControl() {
  const view = deriveMissionControlView(missionState);
  renderStatus(view);
  renderActions(view);
  renderSnapshots(view);
  renderOperationalUnits(view);
  renderTimeline(view);
  byId("missionFreshness").textContent = relativeFreshness(view.freshnessAt);
  const refresh = byId("missionRefreshBtn");
  refresh.disabled = view.loading || view.refreshing;
  refresh.textContent = view.refreshing ? "Aggiornamento..." : "Aggiorna";
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


export function initMissionControl() {
  updateClock();
  clockTimer = window.setInterval(updateClock, 60000);
  byId("missionControlSection").addEventListener("click", handleWorkspaceNavigation);
  byId("missionRefreshBtn").addEventListener("click", () => {
    byId("refreshBriefingBtn").click();
  });
  document.addEventListener("briefing:state-changed", (event) => {
    if (event.detail.phase === "loading") {
      updateMissionControl({ type: "briefing-loading" });
      return;
    }
    if (event.detail.phase === "error") {
      updateMissionControl({
        type: "briefing-failed",
        message: event.detail.errorMessage,
      });
    }
  });
  document.addEventListener("briefing:changed", (event) => {
    updateMissionControl({
      type: "briefing-loaded",
      briefing: event.detail.briefing,
    });
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
  });
  renderMissionControl();
}

import {
  applyWorkforceWeekCopy,
  downloadWorkforceExport,
  getWorkforceCalendar,
  getWorkforceCoverage,
  getWorkforceContactCoverage,
  getWorkforceFoundation,
  getWorkforceStatus,
  listWorkforceMembers,
  previewWorkforceWeekCopy,
  saveWorkforceDayStatus,
  saveWorkforceDayStatusesBatch,
  updateWorkforceMember,
} from "../api.js?v=19";
import {
  byId,
  renderViewState,
  setLoading,
  setMessage,
} from "../utils/dom.js";
import { isExpectedApiError, userErrorPresentation } from "../utils/errors.js";
import {
  renderWorkforceCalendar,
  workforceCellKey,
} from "./workforce-calendar-view.js?v=4";
import {
  nextMultiDaySelection,
  populateWorkforceBulkChoices,
  workforceBulkPayload,
  workforceNavigationDays,
  workforceQuickSelection,
  workforceQuickSelectionActive,
} from "./workforce-multi-day-editor.js?v=3";
import {
  renderWorkforceWeekCopyPreview,
  workforceWeekCopySummary,
} from "./workforce-week-copy.js?v=2";
import { initWorkforceDetailPanel } from "./workforce-detail-panel.js?v=6";
import { initWorkforceImportFlow } from "./workforce-import-flow.js";
import {
  renderWorkforceAnomalies,
  renderWorkforceCoverage,
} from "./workforce-insights-view.js";
import {
  renderWorkforceLanding,
  renderWorkforceActivitySummary,
  renderWorkforceSummary,
  filterWorkforcePlanningMembers,
  workforceActivitySummary,
  workforceCalendarWindow,
  workforceOperationalActivities,
  workforceSummary,
} from "./workforce-view.js";
import { renderWorkforceContactCoverage } from "./workforce-contact-coverage.js?v=1";
import {
  initWorkforceFoundation,
  renderWorkforceFoundation,
} from "./workforce-foundation.js?v=3";
import { initDriverShiftPlanning } from "./driver-shift-planning.js?v=16";
import { initWorkforceMemberCreate } from "./workforce-member-create.js?v=2";


const PAGE_STATES = Object.freeze({
  EMPTY: "empty",
  IMPORTING: "importing",
  READY: "ready",
  ERROR: "error",
});
const TAB_ORDER = ["calendar", "coverage", "anomalies"];
const ANOMALY_PAGE_SIZE = 25;

let loaded = false;
let firstPaintPromise = null;
let calendarLoaded = false;
let currentStatus = null;
let currentData = { members: [], statuses: [], coverage: [] };
let viewMode = "week";
let activeTab = "calendar";
let anomalyLimit = ANOMALY_PAGE_SIZE;
let workforceImportFlow = null;
let workforceDetailPanel = null;
let driverShiftPlanning = null;
let workforceMemberCreate = null;
let feedbackTimeout = null;
let selectedCellKey = null;
let multiDayEditing = {
  memberId: null,
  selectedDates: new Set(),
  anchorDate: null,
  trigger: null,
};
let weekCopyPreview = null;


function errorMessage(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
  return presentation.message;
}


function showWorkforceFeedback(message) {
  const content = `✔ ${message}`;
  window.clearTimeout(feedbackTimeout);
  setMessage(content, "success");
  feedbackTimeout = window.setTimeout(() => {
    if (byId("message").textContent === content) setMessage("");
  }, 3200);
}


function isMobileLayout() {
  return window.matchMedia("(max-width: 720px)").matches;
}


function isoDate(value) {
  return value.toISOString().slice(0, 10);
}


function utcDate(value) {
  return new Date(`${value}T00:00:00Z`);
}


function addDays(value, days) {
  const date = utcDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return isoDate(date);
}


function periodLabel(dateFrom, dateTo) {
  const formatter = new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  return `${formatter.format(utcDate(dateFrom))} – ${formatter.format(utcDate(dateTo))}`;
}


function periodForAnchor(anchor) {
  if (viewMode === "day") return { dateFrom: anchor, dateTo: anchor };
  const date = utcDate(anchor);
  const mondayOffset = (date.getUTCDay() + 6) % 7;
  const dateFrom = addDays(anchor, -mondayOffset);
  return { dateFrom, dateTo: addDays(dateFrom, 6) };
}


function setPageState(state, status = null) {
  byId("workforceSection").dataset.pageState = state;
  byId("workforceViewState").hidden = true;
  byId("workforceReadyView").hidden = true;
  byId("workforceHeaderActions").hidden = true;

  if (state === PAGE_STATES.IMPORTING) {
    renderViewState(byId("workforceViewState"), {
      state: "loading",
      title: "Caricamento Planning turni",
    });
    return;
  }
  if (state === PAGE_STATES.EMPTY) {
    renderViewState(byId("workforceViewState"), {
      state: "empty",
      title: "Planning turni",
      description: "Importa il planning esistente oppure crea il primo planning.",
      actionLabel: "Importa da Excel",
      action: "import-workforce",
      actionTone: "primary",
    });
    byId("workforceViewState").querySelector("[data-view-action]")
      ?.addEventListener("click", () => workforceImportFlow.open());
    return;
  }
  if (state === PAGE_STATES.ERROR) {
    renderViewState(byId("workforceViewState"), {
      state: "error",
      title: "Planning turni non disponibile",
      description: "Non e stato possibile recuperare lo stato. Riprova.",
      actionLabel: "Riprova",
      action: "retry-workforce",
    });
    byId("workforceViewState").querySelector("[data-view-action]")
      ?.addEventListener("click", refresh);
    return;
  }
  if (state === PAGE_STATES.READY) {
    renderWorkforceLanding(status);
    byId("workforceHeaderActions").hidden = false;
    byId("workforceReadyView").hidden = false;
  }
}


function setViewMode(mode) {
  viewMode = mode;
  document.querySelectorAll("[data-workforce-view-mode]").forEach((button) => {
    const active = button.dataset.workforceViewMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}


function renderAnomalies() {
  const result = renderWorkforceAnomalies({
    container: byId("workforceAnomalies"),
    summaryElement: byId("workforceAnomalySummary"),
    categoriesElement: byId("workforceAnomalyCategories"),
    statuses: currentData.statuses,
    members: currentData.members,
    filter: byId("workforceAnomalyFilter").value,
    limit: anomalyLimit,
  });
  byId("workforceAnomaliesMore").hidden = !result.hasMore;
}


function renderActiveTab() {
  if (activeTab === "coverage") {
    renderWorkforceCoverage(byId("workforceCoverage"), currentData.coverage);
  } else if (activeTab === "anomalies") {
    renderAnomalies();
  }
}


function setActiveTab(tab, { focus = false } = {}) {
  activeTab = TAB_ORDER.includes(tab) ? tab : "calendar";
  document.querySelectorAll("[data-workforce-tab]").forEach((button) => {
    const active = button.dataset.workforceTab === activeTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active && focus) button.focus();
  });
  document.querySelectorAll("[data-workforce-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.workforcePanel !== activeTab;
  });
  renderActiveTab();
}


function multiDayMember() {
  return currentData.members.find((item) => (
    Number(item.workforce_member_id) === Number(multiDayEditing.memberId)
  )) || null;
}


function renderMultiDayBar() {
  const member = multiDayMember();
  const count = multiDayEditing.selectedDates.size;
  byId("workforceMultiDayBar").hidden = !member;
  if (!member) return;
  const quickSelection = byId("workforceQuickSelection");
  const weekDates = workforceCalendarDatesForActiveRange();
  quickSelection.hidden = viewMode !== "week";
  byId("workforceWeekCopyOpen").hidden = viewMode !== "week";
  quickSelection.querySelectorAll("[data-workforce-quick-selection]").forEach((button) => {
    button.setAttribute("aria-pressed", String(workforceQuickSelectionActive(
      multiDayEditing.selectedDates,
      weekDates,
      button.dataset.workforceQuickSelection,
    )));
  });
  byId("workforceMultiDayDriver").textContent = member.display_name;
  byId("workforceMultiDayCount").textContent = `${count} ${count === 1 ? "giorno selezionato" : "giorni selezionati"}`;
  byId("workforceMultiDayApply").disabled = count === 0 || !byId("workforceMultiDayChoice").value;
}


function setWeekCopyError(message = "") {
  const element = byId("workforceWeekCopyError");
  element.textContent = message;
  element.hidden = !message;
}


function renderWeekCopyPreview(preview) {
  const summary = workforceWeekCopySummary(preview);
  byId("workforceWeekCopySourcePeriod").textContent = periodLabel(
    preview.source_week_start,
    preview.source_week_end,
  );
  byId("workforceWeekCopyTargetPeriod").textContent = periodLabel(
    preview.target_week_start,
    preview.target_week_end,
  );
  byId("workforceWeekCopySummary").innerHTML = `
    <span><small>Da copiare</small><strong>${summary.copiedCount}</strong></span>
    <span><small>Mancanti</small><strong>${summary.missingCount}</strong></span>
    <span><small>Sostituzioni</small><strong>${summary.overwriteCount}</strong></span>
  `;
  renderWorkforceWeekCopyPreview(byId("workforceWeekCopyRows"), preview);
  byId("workforceWeekCopyConfirm").disabled = summary.copiedCount === 0;
}


async function openWeekCopyPreview() {
  const member = multiDayMember();
  if (!member || viewMode !== "week") return;
  const button = byId("workforceWeekCopyOpen");
  setLoading(button, true, "Preparazione...");
  setWeekCopyError();
  try {
    weekCopyPreview = await previewWorkforceWeekCopy(
      member.workforce_member_id,
      byId("workforceDateFrom").value,
    );
    byId("workforceWeekCopyDriver").textContent = member.display_name;
    renderWeekCopyPreview(weekCopyPreview);
    byId("workforceWeekCopyDialog").showModal();
  } catch (error) {
    errorMessage("workforce.week-copy-preview", error);
  } finally {
    setLoading(button, false);
  }
}


function closeWeekCopyPreview() {
  const dialog = byId("workforceWeekCopyDialog");
  if (dialog.open) dialog.close();
  weekCopyPreview = null;
  setWeekCopyError();
}


async function applyWeekCopy() {
  if (!weekCopyPreview || !multiDayMember()) return;
  const button = byId("workforceWeekCopyConfirm");
  const memberId = Number(multiDayEditing.memberId);
  const targetWeekStart = weekCopyPreview.target_week_start;
  setLoading(button, true, "Copia in corso...");
  setWeekCopyError();
  try {
    await applyWorkforceWeekCopy({
      workforce_member_id: memberId,
      target_week_start: targetWeekStart,
      expected_fingerprint: weekCopyPreview.fingerprint,
    });
    closeWeekCopyPreview();
    await loadCalendar({
      dateFrom: targetWeekStart,
      dateTo: addDays(targetWeekStart, 6),
    });
    const member = currentData.members.find((item) => (
      Number(item.workforce_member_id) === memberId
    ));
    if (member) {
      const trigger = byId("workforceCalendar").querySelector(
        `[data-workforce-member-edit="${memberId}"]`,
      );
      startMultiDayEditing(member, trigger);
    }
    showWorkforceFeedback("Settimana copiata.");
  } catch (error) {
    if (isExpectedApiError(error, {
      statuses: [409],
      codes: ["WORKFORCE_WEEK_COPY_STALE"],
    })) {
      try {
        weekCopyPreview = await previewWorkforceWeekCopy(memberId, targetWeekStart);
        renderWeekCopyPreview(weekCopyPreview);
      } catch (refreshError) {
        errorMessage("workforce.week-copy-refresh", refreshError);
      }
      setWeekCopyError(
        "I turni sono cambiati dall'anteprima. Controlla nuovamente la settimana.",
      );
    } else {
      const message = errorMessage("workforce.week-copy-apply", error);
      setWeekCopyError(message);
    }
  } finally {
    setLoading(button, false);
    button.disabled = !weekCopyPreview
      || workforceWeekCopySummary(weekCopyPreview).copiedCount === 0;
  }
}


function workforceCalendarDatesForActiveRange() {
  const dateFrom = byId("workforceDateFrom").value;
  if (!dateFrom || viewMode !== "week") return [];
  return Array.from({ length: 7 }, (_, offset) => addDays(dateFrom, offset));
}


function applyQuickSelection(preset) {
  if (!multiDayMember() || viewMode !== "week") return;
  const weekDates = workforceCalendarDatesForActiveRange();
  multiDayEditing.selectedDates = workforceQuickSelection(
    multiDayEditing.selectedDates,
    weekDates,
    preset,
  );
  multiDayEditing.anchorDate = null;
  renderData();
}


function clearMultiDayEditing({ restoreFocus = false, rerender = true } = {}) {
  const trigger = multiDayEditing.trigger;
  multiDayEditing = {
    memberId: null,
    selectedDates: new Set(),
    anchorDate: null,
    trigger: null,
  };
  byId("workforceMultiDayBar").hidden = true;
  closeWeekCopyPreview();
  if (rerender && currentData.members.length) renderData();
  if (restoreFocus) trigger?.focus?.();
}


function startMultiDayEditing(member, trigger) {
  if (!member) return;
  selectedCellKey = null;
  workforceDetailPanel.close({ restoreFocus: false });
  multiDayEditing = {
    memberId: Number(member.workforce_member_id),
    selectedDates: new Set(),
    anchorDate: null,
    trigger,
  };
  populateWorkforceBulkChoices(
    byId("workforceMultiDayChoice"),
    currentData.statuses,
  );
  renderData();
  renderMultiDayBar();
}


function toggleMultiDayDate({ date, shiftKey, visibleDates }) {
  const next = nextMultiDaySelection(
    multiDayEditing.selectedDates,
    date,
    visibleDates,
    { shiftKey, anchorDate: multiDayEditing.anchorDate },
  );
  multiDayEditing.selectedDates = next.selectedDates;
  multiDayEditing.anchorDate = next.anchorDate;
  renderData();
  renderMultiDayBar();
}


function renderData() {
  const { members, statuses, coverage } = currentData;
  renderWorkforceSummary(workforceSummary(members, statuses, coverage));
  renderWorkforceActivitySummary(
    byId("workforceActivitySummary"),
    workforceActivitySummary(statuses),
  );
  const cycleFilter = byId("workforcePlanningCycleFilter").value;
  const activityFilter = byId("workforcePlanningActivityFilter").value;
  const visibleMembers = filterWorkforcePlanningMembers(
    members, statuses, cycleFilter, activityFilter,
  );
  renderWorkforceCalendar(
    byId("workforceCalendar"),
    visibleMembers,
    statuses,
    viewMode,
    (details) => {
      selectedCellKey = workforceCellKey(
        details.member.workforce_member_id,
        details.date,
      );
      workforceDetailPanel.openStatus(details);
    },
    workforceDetailPanel.openMember,
    {
      selectedCellKey,
      onSelectCell: (key) => { selectedCellKey = key; },
      dateFrom: byId("workforceDateFrom").value,
      dateTo: byId("workforceDateTo").value,
      editingMemberId: multiDayEditing.memberId,
      multiDayDates: multiDayEditing.selectedDates,
      onStartMultiDayEdit: startMultiDayEditing,
      onToggleMultiDayDate: toggleMultiDayDate,
    },
  );
  renderMultiDayBar();
  renderActiveTab();
}


function updateCurrentStatus(savedStatus) {
  const index = currentData.statuses.findIndex((item) => (
    item.status_id === savedStatus.status_id
    || (
      item.workforce_member_id === savedStatus.workforce_member_id
      && item.date === savedStatus.date
    )
  ));
  currentData.statuses = index === -1
    ? [...currentData.statuses, savedStatus]
    : currentData.statuses.map((item, itemIndex) => (
      itemIndex === index ? savedStatus : item
    ));
}


function focusSelectedCell() {
  if (!selectedCellKey) return;
  const selected = [...byId("workforceCalendar").querySelectorAll("[data-workforce-cell-key]")]
    .find((button) => button.dataset.workforceCellKey === selectedCellKey);
  if (!selected) return;
  selected.focus({ preventScroll: true });
  selected.scrollIntoView({ block: "nearest", inline: "nearest" });
}


async function refreshCoverageAfterStatusSave(dateFrom, dateTo) {
  try {
    const coverage = await getWorkforceCoverage(dateFrom, dateTo);
    if (
      byId("workforceDateFrom").value !== dateFrom
      || byId("workforceDateTo").value !== dateTo
    ) return;
    currentData.coverage = coverage.items;
    renderWorkforceSummary(workforceSummary(
      currentData.members,
      currentData.statuses,
      currentData.coverage,
    ));
    if (activeTab === "coverage") {
      renderWorkforceCoverage(byId("workforceCoverage"), currentData.coverage);
    }
  } catch (error) {
    errorMessage("workforce.load-calendar", error);
  }
}


function fallbackCalendarWindow() {
  const dateFrom = isoDate(new Date());
  return { dateFrom, dateTo: addDays(dateFrom, 6) };
}


function selectedCalendarWindow() {
  const dateFrom = byId("workforceDateFrom").value;
  const dateTo = byId("workforceDateTo").value;
  if (dateFrom && dateTo) return { dateFrom, dateTo };
  const suggested = workforceCalendarWindow(currentStatus?.latest_import);
  const fallback = suggested.dateFrom ? suggested : fallbackCalendarWindow();
  if (viewMode === "day") return { dateFrom: fallback.dateFrom, dateTo: fallback.dateFrom };
  if (viewMode === "week") return periodForAnchor(fallback.dateFrom);
  return fallback;
}


function refreshOperationalActivityControls(statuses) {
  const activities = workforceOperationalActivities(statuses);
  const datalist = byId("workforceOperationalActivityOptions");
  datalist.replaceChildren(...activities.map((activity) => new Option(activity, activity)));
  const filter = byId("workforcePlanningActivityFilter");
  const current = filter.value;
  filter.replaceChildren(new Option("Tutte", "all"), ...activities.map((activity) => (
    new Option(activity, activity)
  )));
  filter.value = activities.includes(current) ? current : "all";
  byId("workforcePlanningActivityFilterLabel").hidden = activities.length === 0;
}


async function loadCalendar(range = null) {
  if (!currentStatus?.member_count) return;
  const { dateFrom, dateTo } = range || selectedCalendarWindow();
  selectedCellKey = null;
  clearMultiDayEditing({ rerender: false });
  workforceDetailPanel.close({ restoreFocus: false });
  byId("workforceDateFrom").value = dateFrom;
  byId("workforceDateTo").value = dateTo;
  byId("workforceDatePicker").value = dateFrom;
  byId("workforceCalendarWindow").textContent = periodLabel(dateFrom, dateTo);
  byId("workforceTimestamp").textContent = `Periodo attivo ${dateFrom} - ${dateTo}`;
  byId("workforceCalendar").innerHTML = `
    <div class="workforce-calendar-loading" aria-busy="true" aria-label="Caricamento calendario">
      <span class="skeleton-block"></span>
      <span class="skeleton-block"></span>
      <span class="skeleton-block"></span>
    </div>
  `;
  try {
    const [members, calendar, coverage, foundation, contactCoverage] = await Promise.all([
      listWorkforceMembers(),
      getWorkforceCalendar(dateFrom, dateTo),
      getWorkforceCoverage(dateFrom, dateTo),
      getWorkforceFoundation(dateFrom),
      getWorkforceContactCoverage(),
    ]);
    currentData = {
      members: members.items,
      statuses: calendar.items,
      coverage: coverage.items,
    };
    refreshOperationalActivityControls(currentData.statuses);
    renderWorkforceFoundation(foundation);
    renderWorkforceContactCoverage(byId("workforceContactCoverage"), contactCoverage);
    anomalyLimit = ANOMALY_PAGE_SIZE;
    renderData();
    calendarLoaded = true;
  } catch (error) {
    byId("workforceCalendar").innerHTML = `
      <div class="workforce-calendar-error">
        <strong>Calendario temporaneamente non disponibile.</strong>
        <button id="workforceCalendarRetry" type="button">Riprova</button>
      </div>
    `;
    byId("workforceCalendarRetry").addEventListener("click", () => loadCalendar({ dateFrom, dateTo }));
    errorMessage("workforce.load-calendar", error);
  }
}


async function refresh() {
  setPageState(PAGE_STATES.IMPORTING);
  try {
    const [status] = await Promise.all([
      getWorkforceStatus(),
      driverShiftPlanning?.refresh(),
    ]);
    currentStatus = status;
    calendarLoaded = false;
    loaded = true;
    if (!status.member_count) {
      byId("workforceTimestamp").textContent = "Nessun planning turni importato.";
      setPageState(PAGE_STATES.EMPTY, status);
    } else {
      setViewMode(isMobileLayout() ? "day" : "week");
      setActiveTab("calendar");
      setPageState(PAGE_STATES.READY, status);
      await loadCalendar();
    }
    document.dispatchEvent(new CustomEvent("workforce:status-changed", {
      detail: { memberCount: status.member_count },
    }));
  } catch (error) {
    const disabled = isExpectedApiError(error, { statuses: [404] });
    if (disabled) {
      byId("workforceSection").dataset.pageState = PAGE_STATES.EMPTY;
      renderViewState(byId("workforceViewState"), {
        state: "empty",
        title: "Workforce non attivo",
        description: "Il Plugin Workforce non e abilitato in questo ambiente.",
      });
    } else {
      setPageState(PAGE_STATES.ERROR);
      errorMessage("workforce.load", error);
    }
    loaded = true;
  }
}


export function prepareWorkforceFirstPaint() {
  if (loaded) return Promise.resolve();
  if (firstPaintPromise) return firstPaintPromise;
  firstPaintPromise = refresh().finally(() => {
    firstPaintPromise = null;
  });
  return firstPaintPromise;
}


export async function openWorkforceDriver(driverId) {
  const canonicalId = Number(driverId);
  if (!Number.isInteger(canonicalId) || canonicalId <= 0) return false;
  await prepareWorkforceFirstPaint();
  const member = currentData.members.find((item) => (
    Number(item.workforce_member_id) === canonicalId
  ));
  if (!member) return false;
  setActiveTab("calendar");
  const trigger = byId("workforceCalendar").querySelector(
    `[data-workforce-member-edit="${canonicalId}"]`,
  );
  workforceDetailPanel.openMember(member, trigger);
  trigger?.scrollIntoView({ block: "nearest", inline: "nearest" });
  return true;
}


async function submitStatus(event) {
  event.preventDefault();
  const submit = event.submitter || byId("workforceStatusSave");
  setLoading(submit, true, "Salvataggio...");
  try {
    const selectedStatus = document.querySelector('[name="workforceStatusCode"]:checked');
    const savedStatus = await saveWorkforceDayStatus(Number(byId("workforceStatusId").value || 0), {
      workforce_member_id: Number(byId("workforceStatusMemberId").value),
      date: byId("workforceStatusDate").value,
      status_code: selectedStatus?.value || "unknown",
      shift_code: byId("workforceShiftCode").value.trim() || null,
      operational_activity: byId("workforceOperationalActivity").value.trim() || null,
      start_time: byId("workforceStartTime").value || null,
      end_time: byId("workforceEndTime").value || null,
      notes: byId("workforceStatusNotes").value.trim() || null,
      source_reference: "manual",
    });
    selectedCellKey = workforceCellKey(
      savedStatus.workforce_member_id,
      savedStatus.date,
    );
    updateCurrentStatus(savedStatus);
    workforceDetailPanel.completeStatusSave();
    renderData();
    window.requestAnimationFrame(focusSelectedCell);
    showWorkforceFeedback("Modifica salvata");
    refreshCoverageAfterStatusSave(
      byId("workforceDateFrom").value,
      byId("workforceDateTo").value,
    );
  } catch (error) {
    errorMessage("workforce.save-status", error);
  } finally {
    setLoading(submit, false);
  }
}


async function applyMultiDayStatus() {
  const button = byId("workforceMultiDayApply");
  const payload = workforceBulkPayload(
    multiDayEditing.memberId,
    multiDayEditing.selectedDates,
    byId("workforceMultiDayChoice").value,
  );
  if (!payload) return;
  payload.notes = byId("workforceMultiDayNotes").value.trim() || null;
  payload.operational_activity = byId("workforceMultiDayActivity").value.trim() || null;
  if (payload.status_code === "available_limited" && !payload.notes) {
    setMessage("Aggiungi una motivazione per la disponibilita con limitazioni.", "warning");
    byId("workforceMultiDayNotes").focus();
    return;
  }
  setLoading(button, true, "Applicazione...");
  try {
    const result = await saveWorkforceDayStatusesBatch(payload);
    result.items.forEach(updateCurrentStatus);
    const count = result.items.length;
    multiDayEditing.selectedDates = new Set();
    multiDayEditing.anchorDate = null;
    byId("workforceMultiDayChoice").value = "";
    byId("workforceMultiDayNotes").value = "";
    byId("workforceMultiDayActivity").value = "";
    renderData();
    showWorkforceFeedback(`${count} ${count === 1 ? "giorno aggiornato" : "giorni aggiornati"}`);
    refreshCoverageAfterStatusSave(
      byId("workforceDateFrom").value,
      byId("workforceDateTo").value,
    );
  } catch (error) {
    errorMessage("workforce.save-status-batch", error);
  } finally {
    setLoading(button, false);
    renderMultiDayBar();
  }
}


async function submitMember(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  try {
    await updateWorkforceMember(Number(byId("workforceMemberId").value), {
      first_name: byId("workforceMemberFirstName").value.trim() || null,
      last_name: byId("workforceMemberLastName").value.trim() || null,
      role: byId("workforceMemberRole").value.trim() || null,
      station: byId("workforceMemberStation").value.trim() || null,
      employment_type: byId("workforceEmploymentType").value.trim() || null,
      operational_cycle: byId("workforceOperationalCycle").value,
      active: byId("workforceMemberActive").value === "true",
      phone: byId("workforceMemberPhone").value.trim() || null,
      email: byId("workforceMemberEmail").value.trim() || null,
      contract_end: byId("workforceContractEnd").value || null,
      weekly_hours: byId("workforceWeeklyHours").value
        ? Number(byId("workforceWeeklyHours").value)
        : null,
      capabilities: byId("workforceCapabilities").value
        .split(",").map((item) => item.trim()).filter(Boolean),
      operational_notes: byId("workforceMemberOperationalNotes").value.trim() || null,
      is_reserve: byId("workforceMemberReserve").checked,
    });
    workforceDetailPanel.close();
    await loadCalendar({
      dateFrom: byId("workforceDateFrom").value,
      dateTo: byId("workforceDateTo").value,
    });
    showWorkforceFeedback("Profilo salvato");
  } catch (error) {
    errorMessage("workforce.save-member", error);
  } finally {
    setLoading(submit, false);
  }
}


function loadFromAnchor(anchor) {
  if (!anchor) return;
  loadCalendar(periodForAnchor(anchor));
}


function shiftCalendar(direction) {
  const current = byId("workforceDateFrom").value || isoDate(new Date());
  loadFromAnchor(addDays(current, workforceNavigationDays(viewMode, direction)));
}


function handleTabKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const currentIndex = TAB_ORDER.indexOf(activeTab);
  const nextIndex = event.key === "Home"
    ? 0
    : event.key === "End"
      ? TAB_ORDER.length - 1
      : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + TAB_ORDER.length) % TAB_ORDER.length;
  setActiveTab(TAB_ORDER[nextIndex], { focus: true });
}


export function initWorkforcePage() {
  initWorkforceFoundation();
  workforceDetailPanel = initWorkforceDetailPanel({
    getStatuses: () => currentData.statuses,
    onSelectionCleared: () => { selectedCellKey = null; },
  });
  workforceImportFlow = initWorkforceImportFlow({
    onImported: async (result, preview) => {
      await driverShiftPlanning?.handleImported(result, preview);
      calendarLoaded = false;
      document.dispatchEvent(new CustomEvent("workforce:data-imported", {
        detail: { datasetType: "workforce" },
      }));
      await refresh();
    },
    onSuccess: showWorkforceFeedback,
  });
  workforceMemberCreate = initWorkforceMemberCreate({
    onCreated: async () => {
      await refresh();
      showWorkforceFeedback("Driver creato");
    },
    onError: (error) => errorMessage("workforce.create-member", error),
  });
  driverShiftPlanning = initDriverShiftPlanning({
    openImport: () => workforceImportFlow.open(),
    getDistributionWindow: () => selectedCalendarWindow(),
    onChanged: async ({ type, periodStart } = {}) => {
      if (type !== "published") return;
      calendarLoaded = false;
      document.dispatchEvent(new CustomEvent("workforce:data-imported", {
        detail: { datasetType: "workforce", source: "driver-shift-planning" },
      }));
      await loadFromAnchor(periodStart || byId("workforceDatePicker").value);
    },
  });
  byId("workforceRefreshBtn").addEventListener("click", () => {
    loadFromAnchor(byId("workforceDatePicker").value);
  });
  byId("workforceDatePicker").addEventListener("change", (event) => {
    loadFromAnchor(event.target.value);
  });
  byId("workforceTodayBtn").addEventListener("click", () => {
    loadFromAnchor(isoDate(new Date()));
  });
  byId("workforcePreviousBtn").addEventListener("click", () => shiftCalendar(-1));
  byId("workforceNextBtn").addEventListener("click", () => shiftCalendar(1));
  byId("workforceExportBtn").addEventListener("click", async () => {
    try {
      await downloadWorkforceExport();
    } catch (error) {
      errorMessage("workforce.export", error);
    }
  });
  byId("workforceStatusEditor").addEventListener("submit", submitStatus);
  byId("workforceMemberEditor").addEventListener("submit", submitMember);
  byId("workforceMultiDayChoice").addEventListener("change", renderMultiDayBar);
  byId("workforcePlanningCycleFilter").addEventListener("change", renderData);
  byId("workforcePlanningActivityFilter").addEventListener("change", renderData);
  byId("workforceMultiDayCancel").addEventListener("click", () => {
    clearMultiDayEditing({ restoreFocus: true });
  });
  byId("workforceMultiDayApply").addEventListener("click", () => {
    void applyMultiDayStatus();
  });
  byId("workforceWeekCopyOpen").addEventListener("click", () => {
    void openWeekCopyPreview();
  });
  byId("workforceWeekCopyConfirm").addEventListener("click", () => {
    void applyWeekCopy();
  });
  byId("workforceWeekCopyCancel").addEventListener("click", closeWeekCopyPreview);
  byId("workforceWeekCopyClose").addEventListener("click", closeWeekCopyPreview);
  byId("workforceWeekCopyDialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    closeWeekCopyPreview();
  });
  byId("workforceQuickSelection").querySelectorAll("[data-workforce-quick-selection]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        applyQuickSelection(button.dataset.workforceQuickSelection);
      });
    });
  document.querySelectorAll("[data-workforce-view-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      setViewMode(button.dataset.workforceViewMode);
      if (calendarLoaded) loadFromAnchor(byId("workforceDatePicker").value);
    });
  });
  document.querySelectorAll("[data-workforce-tab]").forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.workforceTab));
    button.addEventListener("keydown", handleTabKeydown);
  });
  byId("workforceAnomalyFilter").addEventListener("change", () => {
    anomalyLimit = ANOMALY_PAGE_SIZE;
    renderAnomalies();
  });
  byId("workforceAnomaliesMore").addEventListener("click", () => {
    anomalyLimit += ANOMALY_PAGE_SIZE;
    renderAnomalies();
  });
  document.addEventListener("workforce:import-requested", (event) => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "workforce" },
    }));
    const file = event.detail?.file || null;
    workforceImportFlow.open(file, { analyzeFile: Boolean(file) });
  });
  document.addEventListener("workforce:consecutivity-changed", () => {
    if (loaded && currentStatus?.member_count) loadCalendar();
  });
  document.addEventListener("workforce:driver-open", (event) => {
    void openWorkforceDriver(event.detail?.driverId);
  });
  document.addEventListener("workspace:view-changed", (event) => {
    if (event.detail.view === "workforce" && !loaded && !firstPaintPromise) {
      void prepareWorkforceFirstPaint();
    }
  });
  document.addEventListener("workspace:reset-completed", () => {
    loaded = false;
    calendarLoaded = false;
    currentStatus = null;
    currentData = { members: [], statuses: [], coverage: [] };
    selectedCellKey = null;
    clearMultiDayEditing({ rerender: false });
    workforceImportFlow.reset();
    driverShiftPlanning.reset();
    refresh();
  });
}

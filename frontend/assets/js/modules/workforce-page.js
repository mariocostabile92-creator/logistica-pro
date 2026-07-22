import {
  downloadWorkforceExport,
  getWorkforceCalendar,
  getWorkforceCoverage,
  getWorkforceStatus,
  listWorkforceMembers,
  saveWorkforceDayStatus,
  updateWorkforceMember,
} from "../api.js";
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
} from "./workforce-calendar-view.js";
import { initWorkforceDetailPanel } from "./workforce-detail-panel.js";
import { initWorkforceImportFlow } from "./workforce-import-flow.js";
import {
  renderWorkforceAnomalies,
  renderWorkforceCoverage,
} from "./workforce-insights-view.js";
import {
  renderWorkforceLanding,
  renderWorkforceSummary,
  workforceCalendarWindow,
  workforceSummary,
} from "./workforce-view.js";


const PAGE_STATES = Object.freeze({
  EMPTY: "empty",
  IMPORTING: "importing",
  READY: "ready",
  ERROR: "error",
});
const TAB_ORDER = ["calendar", "coverage", "anomalies"];
const ANOMALY_PAGE_SIZE = 25;

let loaded = false;
let calendarLoaded = false;
let currentStatus = null;
let currentData = { members: [], statuses: [], coverage: [] };
let viewMode = "week";
let activeTab = "calendar";
let anomalyLimit = ANOMALY_PAGE_SIZE;
let workforceImportFlow = null;
let workforceDetailPanel = null;
let feedbackTimeout = null;
let selectedCellKey = null;


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


function renderData() {
  const { members, statuses, coverage } = currentData;
  renderWorkforceSummary(workforceSummary(members, statuses, coverage));
  renderWorkforceCalendar(
    byId("workforceCalendar"),
    members,
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
    },
  );
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
  return viewMode === "day"
    ? { dateFrom: fallback.dateFrom, dateTo: fallback.dateFrom }
    : fallback;
}


async function loadCalendar(range = null) {
  if (!currentStatus?.member_count) return;
  const { dateFrom, dateTo } = range || selectedCalendarWindow();
  selectedCellKey = null;
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
    const [members, calendar, coverage] = await Promise.all([
      listWorkforceMembers(),
      getWorkforceCalendar(dateFrom, dateTo),
      getWorkforceCoverage(dateFrom, dateTo),
    ]);
    currentData = {
      members: members.items,
      statuses: calendar.items,
      coverage: coverage.items,
    };
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
    const status = await getWorkforceStatus();
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
      renderViewState(byId("workforceViewState"), {
        state: "empty",
        title: "Workforce non attivo",
        description: "Il Plugin Workforce non e abilitato in questo ambiente.",
      });
    } else {
      setPageState(PAGE_STATES.ERROR);
      errorMessage("workforce.load", error);
    }
  }
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


async function submitMember(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  try {
    await updateWorkforceMember(Number(byId("workforceMemberId").value), {
      role: byId("workforceMemberRole").value.trim() || null,
      employment_type: byId("workforceEmploymentType").value.trim() || null,
      contract_end: byId("workforceContractEnd").value || null,
      weekly_hours: byId("workforceWeeklyHours").value
        ? Number(byId("workforceWeeklyHours").value)
        : null,
      capabilities: byId("workforceCapabilities").value
        .split(",").map((item) => item.trim()).filter(Boolean),
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


function shiftWeek(days) {
  const current = byId("workforceDateFrom").value || isoDate(new Date());
  loadFromAnchor(addDays(current, days));
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
  workforceDetailPanel = initWorkforceDetailPanel({
    getStatuses: () => currentData.statuses,
    onSelectionCleared: () => { selectedCellKey = null; },
  });
  workforceImportFlow = initWorkforceImportFlow({
    onImported: async () => {
      calendarLoaded = false;
      document.dispatchEvent(new CustomEvent("workforce:data-imported", {
        detail: { datasetType: "workforce" },
      }));
      await refresh();
    },
    onSuccess: showWorkforceFeedback,
  });
  byId("workforceRefreshBtn").addEventListener("click", () => {
    loadFromAnchor(byId("workforceDatePicker").value);
  });
  byId("workforceDatePicker").addEventListener("change", (event) => {
    loadFromAnchor(event.target.value);
  });
  byId("workforceTodayBtn").addEventListener("click", () => {
    const suggested = workforceCalendarWindow(currentStatus?.latest_import, new Date());
    const anchor = suggested.dateFrom || isoDate(new Date());
    loadFromAnchor(anchor);
  });
  byId("workforcePreviousBtn").addEventListener("click", () => shiftWeek(-7));
  byId("workforceNextBtn").addEventListener("click", () => shiftWeek(7));
  byId("workforceExportBtn").addEventListener("click", async () => {
    try {
      await downloadWorkforceExport();
    } catch (error) {
      errorMessage("workforce.export", error);
    }
  });
  byId("workforceStatusEditor").addEventListener("submit", submitStatus);
  byId("workforceMemberEditor").addEventListener("submit", submitMember);
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
  document.addEventListener("workspace:view-changed", (event) => {
    if (event.detail.view === "workforce" && !loaded) refresh();
  });
  document.addEventListener("workspace:reset-completed", () => {
    loaded = false;
    calendarLoaded = false;
    currentStatus = null;
    currentData = { members: [], statuses: [], coverage: [] };
    selectedCellKey = null;
    workforceImportFlow.reset();
    refresh();
  });
}

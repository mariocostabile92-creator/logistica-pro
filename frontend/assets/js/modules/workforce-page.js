import {
  downloadWorkforceExport,
  getWorkforceCalendar,
  getWorkforceChanges,
  getWorkforceCoverage,
  getWorkforceStatus,
  listWorkforceMembers,
  saveWorkforceDayStatus,
  updateWorkforceMember,
} from "../api.js";
import { byId, renderViewState, setLoading, setMessage } from "../utils/dom.js";
import { isExpectedApiError, userErrorPresentation } from "../utils/errors.js";
import {
  renderWorkforceCalendar,
  renderWorkforceLanding,
  renderWorkforceLists,
  renderWorkforceSummary,
  workforceCalendarWindow,
  workforceSummary,
} from "./workforce-view.js";
import { initWorkforceImportFlow } from "./workforce-import-flow.js";


const PAGE_STATES = Object.freeze({
  EMPTY: "empty",
  IMPORTING: "importing",
  READY: "ready",
  ERROR: "error",
});

let loaded = false;
let calendarLoaded = false;
let currentStatus = null;
let currentData = { members: [], statuses: [], coverage: [], changes: [] };
let viewMode = "day";
let workforceImportFlow = null;


function errorMessage(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
  return presentation.message;
}


function setPageState(state, status = null) {
  byId("workforceSection").dataset.pageState = state;
  byId("workforceViewState").hidden = true;
  byId("workforceReadyView").hidden = true;
  byId("workforceCalendarView").hidden = true;

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
      title: "Non hai ancora importato un planning turni.",
      description: "Importa il file Excel per iniziare.",
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
    byId("workforceReadyView").hidden = false;
  }
}


function openStatusEditor({ member, status, date }) {
  const form = byId("workforceStatusEditor");
  form.reset();
  byId("workforceStatusId").value = status?.status_id || "";
  byId("workforceStatusMemberId").value = member.workforce_member_id;
  byId("workforceStatusDate").value = status?.date || date;
  byId("workforceStatusCode").value = status?.status_code || "unknown";
  byId("workforceShiftCode").value = status?.shift_code || "";
  byId("workforceStatusNotes").value = status?.notes || "";
  byId("workforceStatusEditorTitle").textContent = member.display_name;
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}


function openMemberEditor(member) {
  const form = byId("workforceMemberEditor");
  form.reset();
  byId("workforceMemberId").value = member.workforce_member_id;
  byId("workforceMemberEditorTitle").textContent = member.display_name;
  byId("workforceMemberRole").value = member.role || "";
  byId("workforceEmploymentType").value = member.employment_type || "";
  byId("workforceContractEnd").value = member.contract_end || "";
  byId("workforceWeeklyHours").value = member.weekly_hours ?? "";
  byId("workforceCapabilities").value = member.capabilities.join(", ");
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}


function renderData() {
  const { members, statuses, coverage, changes } = currentData;
  renderWorkforceSummary(workforceSummary(members, statuses, coverage));
  renderWorkforceCalendar(
    byId("workforceCalendar"),
    members,
    statuses,
    viewMode,
    openStatusEditor,
    openMemberEditor,
  );
  renderWorkforceLists({ members, statuses, coverage, changes });
}


function fallbackCalendarWindow() {
  const start = new Date();
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return {
    dateFrom: start.toISOString().slice(0, 10),
    dateTo: end.toISOString().slice(0, 10),
  };
}


function selectedCalendarWindow(useInputs) {
  if (useInputs) {
    const dateFrom = byId("workforceDateFrom").value;
    const dateTo = byId("workforceDateTo").value;
    if (dateFrom && dateTo) return { dateFrom, dateTo };
  }
  const suggested = workforceCalendarWindow(currentStatus?.latest_import);
  return suggested.dateFrom ? suggested : fallbackCalendarWindow();
}


async function loadCalendar({ useInputs = false } = {}) {
  if (!currentStatus?.member_count) return;
  const { dateFrom, dateTo } = selectedCalendarWindow(useInputs);
  byId("workforceDateFrom").value = dateFrom;
  byId("workforceDateTo").value = dateTo;
  byId("workforceCalendarWindow").textContent = `${dateFrom} - ${dateTo}`;
  byId("workforceCalendarView").hidden = false;
  byId("workforceCalendar").innerHTML = `
    <div class="workforce-calendar-loading" aria-busy="true">
      <span class="skeleton-block"></span>
      <span class="skeleton-block"></span>
    </div>
  `;
  try {
    const [members, calendar, coverage, changes] = await Promise.all([
      listWorkforceMembers(),
      getWorkforceCalendar(dateFrom, dateTo),
      getWorkforceCoverage(dateFrom, dateTo),
      getWorkforceChanges(),
    ]);
    currentData = {
      members: members.items,
      statuses: calendar.items,
      coverage: coverage.items,
      changes: changes.items,
    };
    renderData();
    calendarLoaded = true;
    byId("workforceCalendarView").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    byId("workforceCalendar").innerHTML = `
      <p class="import-notice blocking">Calendario temporaneamente non disponibile.</p>
    `;
    errorMessage("workforce.load-calendar", error);
  }
}


async function refresh() {
  setPageState(PAGE_STATES.IMPORTING);
  try {
    const status = await getWorkforceStatus();
    currentStatus = status;
    calendarLoaded = false;
    byId("workforceTimestamp").textContent = status.latest_import
      ? `Ultimo aggiornamento ${new Date(status.latest_import.imported_at).toLocaleString("it-IT")}`
      : "Nessun planning turni importato.";
    setPageState(status.member_count ? PAGE_STATES.READY : PAGE_STATES.EMPTY, status);
    document.dispatchEvent(new CustomEvent("workforce:status-changed", {
      detail: { memberCount: status.member_count },
    }));
    loaded = true;
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
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  try {
    await saveWorkforceDayStatus(Number(byId("workforceStatusId").value || 0), {
      workforce_member_id: Number(byId("workforceStatusMemberId").value),
      date: byId("workforceStatusDate").value,
      status_code: byId("workforceStatusCode").value,
      shift_code: byId("workforceShiftCode").value.trim() || null,
      notes: byId("workforceStatusNotes").value.trim() || null,
      source_reference: "manual",
    });
    byId("workforceStatusEditor").hidden = true;
    await loadCalendar({ useInputs: true });
    setMessage("Modifica Workforce registrata.", "success");
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
    byId("workforceMemberEditor").hidden = true;
    await loadCalendar({ useInputs: true });
    setMessage("Profilo Workforce aggiornato.", "success");
  } catch (error) {
    errorMessage("workforce.save-member", error);
  } finally {
    setLoading(submit, false);
  }
}


export function initWorkforcePage() {
  workforceImportFlow = initWorkforceImportFlow({
    onImported: async () => {
      calendarLoaded = false;
      document.dispatchEvent(new CustomEvent("operations:data-imported", {
        detail: { datasetType: "workforce" },
      }));
      await refresh();
    },
  });
  byId("workforceOpenCalendarBtn").addEventListener("click", () => loadCalendar());
  byId("workforceCalendarClose").addEventListener("click", () => {
    byId("workforceCalendarView").hidden = true;
    byId("workforceReadyView").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  byId("workforceRefreshBtn").addEventListener("click", () => loadCalendar({ useInputs: true }));
  byId("workforceExportBtn").addEventListener("click", async () => {
    try {
      await downloadWorkforceExport();
    } catch (error) {
      errorMessage("workforce.export", error);
    }
  });
  byId("workforceStatusEditor").addEventListener("submit", submitStatus);
  byId("workforceStatusCancel").addEventListener("click", () => {
    byId("workforceStatusEditor").hidden = true;
  });
  byId("workforceMemberEditor").addEventListener("submit", submitMember);
  byId("workforceMemberCancel").addEventListener("click", () => {
    byId("workforceMemberEditor").hidden = true;
  });
  document.querySelectorAll("[data-workforce-view-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      viewMode = button.dataset.workforceViewMode;
      document.querySelectorAll("[data-workforce-view-mode]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      if (calendarLoaded) renderData();
    });
  });
  document.addEventListener("workforce:import-requested", (event) => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "workforce", targetId: "workforceImportPanel" },
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
    workforceImportFlow.reset();
    refresh();
  });
}

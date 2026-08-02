import { getJournalArchiveDay, getJournalArchiveMonth } from "../../api.js";
import { escapeHtml } from "../../utils/dom.js";
import {
  journalArchiveState as state, moveMonth, resetToOperationalToday,
} from "./state.js";
import { archiveShell, renderDay, renderMonth } from "./renderer.js";

let container;
let filterTimer;

function adoptMonthContext(response) {
  state.month = response.month;
  state.currentOperationalDate = response.context.operational_date;
  if (!state.selectedDate || !state.selectedDate.startsWith(`${state.month}-`)) {
    state.selectedDate = state.currentOperationalDate?.startsWith(`${state.month}-`)
      ? state.currentOperationalDate
      : response.days[0]?.date || `${state.month}-01`;
  }
}

async function loadMonth() {
  container.querySelector(".gdb-calendar-panel").setAttribute("aria-busy", "true");
  try {
    state.monthData = await getJournalArchiveMonth(state.month);
    adoptMonthContext(state.monthData);
    renderMonth(container, state);
  } catch (error) {
    container.querySelector("[data-gdb-calendar]").innerHTML = `<div class="jcr-empty"><strong>Calendario non disponibile</strong><p>${escapeHtml(error.message)}</p><button type="button" data-gdb-retry>Riprova</button></div>`;
  }
}

async function loadDay(preferredId = state.selected?.id) {
  if (!state.selectedDate) return;
  container.querySelector(".gdb-day-panel").setAttribute("aria-busy", "true");
  try {
    state.dayData = await getJournalArchiveDay(state.selectedDate, state.filters);
    state.selected = state.dayData.items.find(item => item.id === preferredId) || state.dayData.items[0] || null;
    renderDay(container, state);
  } catch (error) {
    container.querySelector("[data-gdb-list]").innerHTML = `<div class="jcr-empty"><strong>Storico non disponibile</strong><p>${escapeHtml(error.message)}</p><button type="button" data-gdb-retry>Riprova</button></div>`;
    container.querySelector(".gdb-day-panel").setAttribute("aria-busy", "false");
  }
}

function syncFilterForm() {
  const form = container.querySelector("[data-gdb-filters]");
  for (const element of form.elements) {
    if (element.name) element.value = state.filters[element.name] || "";
  }
}

async function loadSelectedMonth() {
  await loadMonth();
  await loadDay();
}

export async function mountJournalArchive(root) {
  container = root;
  state.filters = {};
  state.activeKpi = "";
  state.selected = null;
  container.innerHTML = archiveShell();
  await loadSelectedMonth();
  container.onclick = async event => {
    const month = event.target.closest("[data-gdb-month]");
    if (month) { moveMonth(Number(month.dataset.gdbMonth)); await loadSelectedMonth(); }
    if (event.target.closest("[data-gdb-today]")) { resetToOperationalToday(); await loadSelectedMonth(); }
    const day = event.target.closest("[data-gdb-date]");
    if (day) { state.selectedDate = day.dataset.gdbDate; state.selected = null; renderMonth(container, state); await loadDay(); }
    const item = event.target.closest("[data-jcr-id]");
    if (item) await loadDay(item.dataset.jcrId);
    const kpi = event.target.closest("[data-gdb-kpi]")?.dataset.gdbKpi;
    if (kpi !== undefined) {
      state.activeKpi = kpi;
      state.filters = kpi === "check_out" || kpi === "check_in" ? { operation_type: kpi }
        : kpi === "anomaly" ? { anomaly: "with" } : kpi === "media" ? { media: "with" }
        : kpi ? { status: kpi } : {};
      syncFilterForm();
      await loadDay();
    }
    if (event.target.closest("[data-gdb-retry]")) await loadSelectedMonth();
    if (event.target.closest("[data-jcr-back]")) container.querySelector(".gdb-master-detail").classList.remove("detail-open");
  };
  container.oninput = event => {
    if (!event.target.closest("[data-gdb-filters]")) return;
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
      const form = new FormData(container.querySelector("[data-gdb-filters]"));
      state.filters = Object.fromEntries([...form].filter(([, value]) => value));
      state.activeKpi = "";
      loadDay();
    }, 180);
  };
  container.onreset = () => {
    state.filters = {};
    state.activeKpi = "";
    setTimeout(loadDay);
  };
  container.addEventListener("journal:media-deleted", () => loadDay());
}

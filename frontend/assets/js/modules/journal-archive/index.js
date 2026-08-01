import { getJournalArchiveDay, getJournalArchiveMonth } from "../../api.js";
import { escapeHtml } from "../../utils/dom.js";
import { journalArchiveState as state, moveMonth, resetToToday } from "./state.js";
import { archiveShell, renderDay, renderMonth } from "./renderer.js";

let container;

async function loadMonth() {
  container.querySelector(".gdb-calendar-panel").setAttribute("aria-busy", "true");
  try {
    state.monthData = await getJournalArchiveMonth(state.month);
    renderMonth(container, state);
  } catch (error) {
    container.querySelector("[data-gdb-calendar]").innerHTML = `<div class="jcr-empty"><strong>Calendario non disponibile</strong><p>${escapeHtml(error.message)}</p><button type="button" data-gdb-retry>Riprova</button></div>`;
  }
}

async function loadDay(preferredId = state.selected?.id) {
  container.querySelector(".gdb-day-panel").setAttribute("aria-busy", "true");
  try {
    state.dayData = await getJournalArchiveDay(state.selectedDate, state.filters);
    state.selected = state.dayData.items.find(item => item.id === preferredId) || state.dayData.items[0] || null;
    renderDay(container, state);
  } catch (error) {
    container.querySelector("[data-gdb-list]").innerHTML = `<div class="jcr-empty"><strong>Storico non disponibile</strong><p>${escapeHtml(error.message)}</p><button type="button" data-gdb-retry>Riprova</button></div>`;
  }
}

export async function mountJournalArchive(root) {
  container = root;
  container.innerHTML = archiveShell();
  await Promise.all([loadMonth(), loadDay()]);
  container.onclick = async event => {
    const month = event.target.closest("[data-gdb-month]");
    if (month) { moveMonth(Number(month.dataset.gdbMonth)); await loadMonth(); }
    if (event.target.closest("[data-gdb-today]")) { resetToToday(); await Promise.all([loadMonth(), loadDay()]); }
    const day = event.target.closest("[data-gdb-date]");
    if (day) { state.selectedDate = day.dataset.gdbDate; state.selected = null; renderMonth(container, state); await loadDay(); }
    const item = event.target.closest("[data-jcr-id]");
    if (item) await loadDay(item.dataset.jcrId);
    const kpi = event.target.closest("[data-gdb-kpi]")?.dataset.gdbKpi;
    if (kpi !== undefined) {
      state.filters = kpi === "check_out" || kpi === "check_in" ? { operation_type: kpi }
        : kpi === "anomaly" ? { anomaly: "with" } : kpi === "media" ? { media: "with" }
        : kpi ? { status: kpi } : {};
      await loadDay();
    }
    if (event.target.closest("[data-gdb-retry]")) await Promise.all([loadMonth(), loadDay()]);
    if (event.target.closest("[data-jcr-back]")) container.querySelector(".gdb-master-detail").classList.remove("detail-open");
  };
  container.oninput = event => {
    if (!event.target.closest("[data-gdb-filters]")) return;
    const form = new FormData(container.querySelector("[data-gdb-filters]"));
    state.filters = Object.fromEntries([...form].filter(([, value]) => value));
    loadDay();
  };
  container.onreset = () => { state.filters = {}; setTimeout(loadDay); };
  container.addEventListener("journal:media-deleted", () => loadDay());
}

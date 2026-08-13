import { saveWorkforceDayMemberBatch } from "../api.js?v=21";
import { escapeHtml } from "../utils/dom.js";
import { workforceBulkChoices } from "./workforce-multi-day-editor.js?v=3";
import {
  clearWorkforcePlanningSelection,
  createWorkforceDayPlannerState,
  focusWorkforcePlanningDay,
  toggleWorkforcePlanningMember,
} from "./workforce-day-planner-state.js?v=2";
import {
  filterWorkforceDayMembers,
  workforceCoverageImpact,
  workforceDayAvailability,
  workforceDayBatchPayload,
  workforceDayCounts,
  workforceDayCoverage,
  workforceDayExitWarning,
  workforceDayStatusMap,
  workforceProtectedStatus,
  workforceWeekProgress,
} from "./workforce-day-planner-presenter.js?v=2";
import {
  planningCoverageDetails,
  planningCoveragePrimaryMessage,
} from "./workforce-coverage-presenter.js";
import { workforceStatusLabel } from "./workforce-view.js";


const FILTERS = Object.freeze([
  ["all", "all", "Tutti"],
  ["cycle", "NEXT_DAY", "Next Day"],
  ["cycle", "SAME_DAY", "Same Day"],
  ["cycle", "NOT_SET", "Non impostato"],
  ["assignment", "unassigned", "Non assegnati"],
  ["assignment", "assigned", "Assegnati"],
  ["assignment", "rest", "Riposo"],
  ["assignment", "absence", "Ferie/assenze"],
]);


function longDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


function shortDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "short", day: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


function addDays(value, amount) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}


function cycleLabel(value) {
  return ({ NEXT_DAY: "NEXT DAY", SAME_DAY: "SAME DAY", NOT_SET: "NON IMPOSTATO" })[value]
    || "NON IMPOSTATO";
}


function options(choices, selected = "") {
  return ['<option value="">Scegli turno o stato</option>', ...choices.map((choice) => (
    `<option value="${escapeHtml(choice.value)}"${choice.value === selected ? " selected" : ""}>${escapeHtml(choice.label)}</option>`
  ))].join("");
}


function quickChoices(choices) {
  const shifts = choices.filter((choice) => choice.value.startsWith("shift:")).slice(0, 4);
  const rest = choices.find((choice) => choice.value === "status:rest");
  return rest ? [...shifts, rest] : shifts;
}


function renderCoverage(response, date) {
  const day = workforceDayCoverage(response, date);
  return day.buckets.map((bucket) => {
    const item = bucket.item;
    const status = item?.coverage_status || "NO_FORECAST";
    return `
      <article class="workforce-day-coverage-card is-${status.toLowerCase().replaceAll("_", "-")}">
        <strong>${escapeHtml(bucket.label)}</strong>
        <dl>
          <div><dt>Forecast</dt><dd>${item?.forecast_routes ?? "—"}</dd></div>
          <div><dt>Requirement</dt><dd>${item?.required_capacity ?? "—"}</dd></div>
          <div><dt>Assegnati</dt><dd>${item?.assigned_drivers ?? 0}</dd></div>
        </dl>
        <b>${escapeHtml(planningCoveragePrimaryMessage(item))}</b>
        <small>${escapeHtml(planningCoverageDetails(item))}</small>
      </article>
    `;
  }).join("");
}


function renderProgress(response, focusedDate) {
  const symbols = { COMPLETE: "✓", REQUIREMENT_GAP: "⚠", FORECAST_GAP: "●", NO_FORECAST: "—" };
  return workforceWeekProgress(response).map((item) => `
    <button type="button" data-day-planner-date="${item.date}" class="is-${item.status.toLowerCase()}${item.date === focusedDate ? " is-active" : ""}" aria-pressed="${item.date === focusedDate}">
      <span>${escapeHtml(shortDate(item.date))}</span><b aria-hidden="true">${symbols[item.status]}</b>
    </button>
  `).join("");
}


function renderImpact(response, state, data, choice = "") {
  const impact = workforceCoverageImpact(
    response,
    state.focusedDate,
    data.members,
    data.statuses,
    state.selectedMemberIds,
    choice,
  );
  if (!choice) return "Seleziona un turno per stimare l'impatto sulla coverage.";
  if (!impact.length) return "Il turno selezionato non incrementa i bucket coverage correnti.";
  return impact.map((item) => {
    const next = item.current + item.added;
    const gap = item.requirement === null ? "requirement non disponibile"
      : `gap ${Math.max(Number(item.requirement) - next, 0)}`;
    return `${item.label}: +${item.added} (${item.current} → ${next}, ${gap})`;
  }).join(" · ");
}


function renderDriver(member, status, state, choices) {
  const id = Number(member.workforce_member_id);
  const selected = state.selectedMemberIds.has(id);
  const expanded = state.expandedMemberId === id;
  const availability = workforceDayAvailability(status);
  const current = status?.shift_code || workforceStatusLabel(status?.status_code || "unknown");
  return `
    <article class="workforce-day-driver${selected ? " is-selected" : ""}${availability.warning ? " has-warning" : ""}" data-day-driver="${id}">
      <label class="workforce-day-driver-select">
        <input type="checkbox" data-day-member-select="${id}" ${selected ? "checked" : ""} />
        <span class="visually-hidden">Seleziona ${escapeHtml(member.display_name)}</span>
      </label>
      <div class="workforce-day-driver-identity">
        <strong>${escapeHtml(member.display_name)}</strong>
        <small>${escapeHtml(member.external_identifier || "ID non disponibile")}</small>
      </div>
      <div class="workforce-day-driver-meta">
        <span>${escapeHtml(cycleLabel(member.operational_cycle || "NOT_SET"))}</span>
        <span>${escapeHtml(member.employment_type || "Contratto non indicato")}</span>
      </div>
      <div class="workforce-day-driver-assignment">
        <strong>${escapeHtml(current)}</strong>
        <small>${escapeHtml(status?.operational_activity || "Nessuna attività")}</small>
      </div>
      <span class="workforce-day-availability is-${availability.tone}">${escapeHtml(availability.label)}</span>
      <button type="button" class="quiet" data-day-inline-open="${id}" aria-expanded="${expanded}">Modifica</button>
      ${expanded ? `
        <div class="workforce-day-inline-editor" data-day-inline-editor="${id}">
          <div class="workforce-day-quick-assign" aria-label="Azioni rapide">${quickChoices(choices).map((choice) => `<button type="button" class="quiet" data-day-inline-quick="${escapeHtml(choice.value)}">${escapeHtml(choice.label)}</button>`).join("")}</div>
          <label>Turno o stato<select data-day-inline-choice>${options(choices, status?.shift_code ? `shift:${status.shift_code}` : `status:${status?.status_code || ""}`)}</select></label>
          <label>Attività<input data-day-inline-activity maxlength="160" list="workforceOperationalActivityOptions" value="${escapeHtml(status?.operational_activity || "")}" /></label>
          <label>Nota<input data-day-inline-notes maxlength="1000" value="${escapeHtml(status?.notes || "")}" /></label>
          <button type="button" data-day-inline-save="${id}">Salva</button>
        </div>
      ` : ""}
    </article>
  `;
}


export function createWorkforceDayPlanner({
  container,
  liveRegion,
  getData,
  getRange,
  getCoverage,
  applyBatch = saveWorkforceDayMemberBatch,
  onNavigate = async () => {},
  onApplied = async () => null,
}) {
  let state = createWorkforceDayPlannerState();
  let searchTimer = null;
  let pendingPayload = null;

  function data() {
    const current = getData() || {};
    return { members: current.members || [], statuses: current.statuses || [] };
  }

  function choices() {
    return workforceBulkChoices(data().statuses);
  }

  function activities() {
    return [...new Set(data().statuses.map((item) => String(item.operational_activity || "").trim()).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right, "it-IT"));
  }

  function visibleMembers() {
    const current = data();
    return filterWorkforceDayMembers(
      current.members,
      current.statuses,
      state.focusedDate,
      state,
    );
  }

  function render({ preserveFocus = false } = {}) {
    if (container.hidden || !state.focusedDate) return;
    const active = preserveFocus ? document.activeElement : null;
    const activeId = active?.id || "";
    const selectionStart = active?.selectionStart;
    const scroll = container.querySelector("[data-day-driver-list]")?.scrollTop || 0;
    const current = data();
    const statusByMember = workforceDayStatusMap(current.statuses, state.focusedDate);
    const members = visibleMembers();
    const counts = workforceDayCounts(current.members, current.statuses, state.focusedDate);
    const coverage = getCoverage();
    const shiftChoices = choices();
    const recentActivities = activities();
    const range = getRange();
    const previousDisabled = !range?.dateFrom;
    container.innerHTML = `
      <header class="workforce-day-planner-header">
        <div><p class="eyebrow">Pianifica giornata</p><h3>${escapeHtml(longDate(state.focusedDate))}</h3><p>Assegna rapidamente turno e attività, poi verifica la coverage.</p></div>
        <div><button type="button" class="quiet" data-day-planner-close>Chiudi</button></div>
      </header>
      <nav class="workforce-day-week-progress" aria-label="Avanzamento settimana">${renderProgress(coverage, state.focusedDate)}</nav>
      <div class="workforce-day-navigation">
        <button type="button" data-day-planner-move="-1" ${previousDisabled ? "disabled" : ""}>Giorno precedente</button>
        <button type="button" data-day-planner-move="1">Giorno successivo</button>
      </div>
      <section class="workforce-day-coverage" aria-label="Coverage del giorno">${renderCoverage(coverage, state.focusedDate)}</section>
      <dl class="workforce-day-counts">
        <div><dt>Totali</dt><dd>${counts.total}</dd></div><div><dt>Assegnati</dt><dd>${counts.assigned}</dd></div>
        <div><dt>Non assegnati</dt><dd>${counts.unassigned}</dd></div><div><dt>Assenti</dt><dd>${counts.absent}</dd></div>
        <div><dt>Disponibili</dt><dd>${counts.available}</dd></div>
      </dl>
      <div class="workforce-day-tools">
        <label>Cerca driver<input id="workforceDaySearch" type="search" value="${escapeHtml(state.search)}" placeholder="Nome, ID, Transporter ID" autocomplete="off" /></label>
        ${recentActivities.length ? `<label>Attività<select id="workforceDayActivityFilter"><option value="all">Tutte</option>${recentActivities.map((activity) => `<option value="${escapeHtml(activity)}"${state.activityFilter === activity ? " selected" : ""}>${escapeHtml(activity)}</option>`).join("")}</select></label>` : ""}
      </div>
      <div class="workforce-day-fast-filters" aria-label="Filtri rapidi">${FILTERS.map(([group, value, label]) => {
        const active = group === "all"
          ? state.cycleFilter === "all" && state.assignmentFilter === "all"
          : group === "cycle" ? state.cycleFilter === value : state.assignmentFilter === value;
        return `<button type="button" data-day-filter-group="${group}" data-day-filter="${value}" aria-pressed="${active}">${label}</button>`;
      }).join("")}</div>
      <div class="workforce-day-list-heading"><strong>${members.length} driver</strong><label><input type="checkbox" data-day-select-visible ${members.length > 0 && members.every((member) => state.selectedMemberIds.has(Number(member.workforce_member_id))) ? "checked" : ""} /> Seleziona visibili</label></div>
      <div class="workforce-day-driver-list" data-day-driver-list>${members.length ? members.map((member) => renderDriver(member, statusByMember.get(Number(member.workforce_member_id)), state, shiftChoices)).join("") : '<p class="empty-state">Nessun driver corrisponde ai filtri.</p>'}</div>
      <section class="workforce-day-action-bar" ${state.selectedMemberIds.size ? "" : "hidden"}>
        <div><strong>${state.selectedMemberIds.size} driver selezionati</strong><small data-day-impact>${escapeHtml(renderImpact(coverage, state, current))}</small></div>
        <div class="workforce-day-action-control"><label for="workforceDayBatchChoice">Turno o stato</label><select id="workforceDayBatchChoice">${options(shiftChoices)}</select><span class="workforce-day-action-picks">${quickChoices(shiftChoices).map((choice) => `<button type="button" class="quiet" data-day-batch-quick="${escapeHtml(choice.value)}">${escapeHtml(choice.label)}</button>`).join("")}</span></div>
        <div class="workforce-day-action-control"><label for="workforceDayBatchActivity">Attività</label><input id="workforceDayBatchActivity" maxlength="160" list="workforceOperationalActivityOptions" placeholder="Facoltativa" />${recentActivities.length ? `<span class="workforce-day-action-picks">${recentActivities.slice(0, 4).map((activity) => `<button type="button" class="quiet" data-day-activity-quick="${escapeHtml(activity)}">${escapeHtml(activity)}</button>`).join("")}</span>` : ""}</div>
        <label>Nota<input id="workforceDayBatchNotes" maxlength="1000" placeholder="Facoltativa" /></label>
        <label>Policy<select id="workforceDayOverwritePolicy"><option value="APPLY_TO_EMPTY_ONLY">Solo celle vuote</option><option value="REPLACE_SELECTED">Sostituisci selezionati</option></select></label>
        <div><button type="button" class="quiet" data-day-selection-cancel>Annulla</button><button type="button" data-day-batch-apply>Applica</button></div>
      </section>
      <p class="workforce-day-error" data-day-error role="alert" hidden></p>
      <dialog class="workforce-day-confirm" data-day-confirm>
        <h3>Conferma sostituzione</h3><p data-day-confirm-message></p>
        <div><button type="button" class="quiet" data-day-confirm-cancel>Annulla</button><button type="button" data-day-confirm-apply>Conferma e applica</button></div>
      </dialog>
    `;
    const list = container.querySelector("[data-day-driver-list]");
    if (list) list.scrollTop = scroll;
    if (preserveFocus && activeId) {
      const target = container.querySelector(`#${activeId}`);
      target?.focus({ preventScroll: true });
      if (Number.isInteger(selectionStart) && target?.setSelectionRange) target.setSelectionRange(selectionStart, selectionStart);
    }
  }

  function showError(message = "") {
    const error = container.querySelector("[data-day-error]");
    if (!error) return;
    error.textContent = message;
    error.hidden = !message;
  }

  function updateImpactPreview() {
    const target = container.querySelector("[data-day-impact]");
    if (!target) return;
    target.textContent = renderImpact(
      getCoverage(),
      state,
      data(),
      container.querySelector("#workforceDayBatchChoice")?.value || "",
    );
  }

  async function submit(payload) {
    if (!payload) return;
    state.loading = true;
    showError();
    container.querySelectorAll("button, select, input").forEach((control) => { control.disabled = true; });
    try {
      const result = await applyBatch(payload);
      state = clearWorkforcePlanningSelection(state);
      const coverage = await onApplied(result);
      liveRegion.textContent = `${result.applied_count} assegnazioni salvate. Coverage aggiornata.`;
      render();
      return coverage;
    } catch (error) {
      showError(error?.message || "Impossibile applicare le assegnazioni.");
    } finally {
      state.loading = false;
      container.querySelectorAll("button, select, input").forEach((control) => { control.disabled = false; });
    }
  }

  function prepareApply(memberIds, source) {
    const current = data();
    const byMember = workforceDayStatusMap(current.statuses, state.focusedDate);
    const choice = source.querySelector("[data-day-inline-choice]")?.value
      || container.querySelector("#workforceDayBatchChoice")?.value;
    const activity = source.querySelector("[data-day-inline-activity]")?.value
      || container.querySelector("#workforceDayBatchActivity")?.value;
    const notes = source.querySelector("[data-day-inline-notes]")?.value
      || container.querySelector("#workforceDayBatchNotes")?.value;
    const overwritePolicy = source.querySelector("#workforceDayOverwritePolicy")?.value || "REPLACE_SELECTED";
    const payload = workforceDayBatchPayload({
      date: state.focusedDate,
      memberIds,
      choice,
      activity,
      notes,
      overwritePolicy,
    });
    if (!payload) {
      showError("Seleziona almeno un driver e un turno o stato.");
      return;
    }
    const existing = memberIds.filter((id) => byMember.has(Number(id)));
    const protectedIds = memberIds.filter((id) => workforceProtectedStatus(byMember.get(Number(id))));
    if (overwritePolicy === "REPLACE_SELECTED" && existing.length) {
      pendingPayload = {
        ...payload,
        confirm_overwrite: true,
        confirm_unavailable_override: protectedIds.length > 0,
      };
      const dialog = container.querySelector("[data-day-confirm]");
      dialog.querySelector("[data-day-confirm-message]").textContent = protectedIds.length
        ? `${existing.length} driver hanno dati esistenti; ${protectedIds.length} risultano in riposo, ferie o assenza. Confermi l'override?`
        : `${existing.length} driver hanno già un turno o stato. Confermi la sostituzione?`;
      dialog.showModal();
      return;
    }
    void submit(payload);
  }

  async function navigate(date) {
    const warning = workforceDayExitWarning(getCoverage(), state.focusedDate);
    if (warning && !window.confirm(`${warning}\nVuoi passare comunque al giorno selezionato?`)) return;
    state = focusWorkforcePlanningDay(state, date);
    await onNavigate(date);
    render();
  }

  container.addEventListener("click", (event) => {
    const close = event.target.closest("[data-day-planner-close]");
    if (close) { container.hidden = true; state = clearWorkforcePlanningSelection(state); return; }
    const dateButton = event.target.closest("[data-day-planner-date]");
    if (dateButton) { void navigate(dateButton.dataset.dayPlannerDate); return; }
    const move = event.target.closest("[data-day-planner-move]");
    if (move) { void navigate(addDays(state.focusedDate, Number(move.dataset.dayPlannerMove))); return; }
    const filter = event.target.closest("[data-day-filter]");
    if (filter) {
      const group = filter.dataset.dayFilterGroup;
      const value = filter.dataset.dayFilter;
      if (group === "all") {
        state.cycleFilter = "all";
        state.assignmentFilter = "all";
      } else if (group === "cycle") {
        state.cycleFilter = state.cycleFilter === value ? "all" : value;
      } else {
        state.assignmentFilter = state.assignmentFilter === value ? "all" : value;
      }
      state.selectedMemberIds = new Set();
      render();
      return;
    }
    const inline = event.target.closest("[data-day-inline-open]");
    if (inline) { state.expandedMemberId = state.expandedMemberId === Number(inline.dataset.dayInlineOpen) ? null : Number(inline.dataset.dayInlineOpen); render(); return; }
    const inlineSave = event.target.closest("[data-day-inline-save]");
    if (inlineSave) { prepareApply([Number(inlineSave.dataset.dayInlineSave)], inlineSave.closest("[data-day-inline-editor]")); return; }
    const inlineQuick = event.target.closest("[data-day-inline-quick]");
    if (inlineQuick) { inlineQuick.closest("[data-day-inline-editor]").querySelector("[data-day-inline-choice]").value = inlineQuick.dataset.dayInlineQuick; return; }
    const batchQuick = event.target.closest("[data-day-batch-quick]");
    if (batchQuick) { container.querySelector("#workforceDayBatchChoice").value = batchQuick.dataset.dayBatchQuick; updateImpactPreview(); return; }
    const activityQuick = event.target.closest("[data-day-activity-quick]");
    if (activityQuick) { container.querySelector("#workforceDayBatchActivity").value = activityQuick.dataset.dayActivityQuick; return; }
    if (event.target.closest("[data-day-selection-cancel]")) { state = clearWorkforcePlanningSelection(state); render(); return; }
    if (event.target.closest("[data-day-batch-apply]")) { prepareApply([...state.selectedMemberIds], container); return; }
    if (event.target.closest("[data-day-confirm-cancel]")) { pendingPayload = null; container.querySelector("[data-day-confirm]").close(); return; }
    if (event.target.closest("[data-day-confirm-apply]")) { const payload = pendingPayload; pendingPayload = null; container.querySelector("[data-day-confirm]").close(); void submit(payload); }
  });

  container.addEventListener("change", (event) => {
    if (event.target.matches("[data-day-member-select]")) {
      state = toggleWorkforcePlanningMember(state, Number(event.target.dataset.dayMemberSelect));
      render();
    }
    if (event.target.matches("[data-day-select-visible]")) {
      const ids = visibleMembers().map((member) => Number(member.workforce_member_id));
      state.selectedMemberIds = event.target.checked ? new Set(ids) : new Set();
      render();
    }
    if (event.target.id === "workforceDayActivityFilter") {
      state.activityFilter = event.target.value;
      state.selectedMemberIds = new Set();
      render();
    }
    if (event.target.id === "workforceDayBatchChoice") updateImpactPreview();
  });

  container.addEventListener("input", (event) => {
    if (event.target.id !== "workforceDaySearch") return;
    window.clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = window.setTimeout(() => {
      state.search = value;
      state.selectedMemberIds = new Set();
      render({ preserveFocus: true });
    }, 120);
  });

  return {
    open(date) {
      container.hidden = false;
      state = focusWorkforcePlanningDay(state, date || getRange()?.dateFrom || "");
      render();
      container.scrollIntoView({ block: "start", behavior: "smooth" });
    },
    focusDate(date) {
      if (!date) return;
      state = focusWorkforcePlanningDay(state, date);
      render();
    },
    refresh() { render(); },
    getState: () => ({ ...state, selectedMemberIds: new Set(state.selectedMemberIds) }),
  };
}

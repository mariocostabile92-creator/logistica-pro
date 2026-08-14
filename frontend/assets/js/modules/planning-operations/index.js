import { planningOperationsApi } from "./api.js";
import { renderOperations, renderOperationsLoading, renderRouteList } from "./renderer.js?v=fleet2";
import { filteredRoutes, planningOperationsState as state } from "./state.js";
import { userMessageForError } from "../../utils/errors.js";
import {
  addOperationalDays,
  operationalWeek,
  todayOperationalDate,
} from "./day-navigation.js?v=day1";
import {
  changedRequirements,
  forecastDraft,
  requirementPreview,
} from "./forecast-editor.js?v=forecast2";

let root;
let initialLoadPromise = null;
let loadSequence = 0;

function syncDateUrl(operationDate) {
  const url = new URL(window.location.href);
  url.searchParams.set("planning_date", operationDate);
  history.replaceState(history.state, "", url);
}

function renderCurrent() {
  renderOperations(root, state.payload, filteredRoutes(state), {
    weekPayloads: state.weekPayloads,
    weekLoading: state.weekLoading,
    weekError: state.weekError,
    forecastEditor: state.forecastEditor,
  });
}

function resetForecastEditor() {
  state.forecastEditor = {
    open: false,
    saving: false,
    error: null,
    draft: null,
    initial: null,
  };
}

function openForecastEditor() {
  const draft = forecastDraft(state.payload.coverage);
  state.forecastEditor = {
    open: true,
    saving: false,
    error: null,
    draft,
    initial: { ...draft },
  };
  renderCurrent();
  root.querySelector("[data-manual-coverage-input]")?.focus();
}

function closeForecastEditor() {
  if (state.forecastEditor.saving) return;
  resetForecastEditor();
  renderCurrent();
}

async function load(operationDate = state.selectedOperationalDate || todayOperationalDate()) {
  const sequence = ++loadSequence;
  state.selectedOperationalDate = operationDate;
  root.setAttribute("aria-busy", "true");
  try {
    const payload = await planningOperationsApi.load({ operationDate });
    if (sequence !== loadSequence) return;
    state.payload = payload;
    state.selectedOperationalDate = payload.operation_date;
    state.weekPayloads.set(payload.operation_date, payload);
    renderCurrent();
    const diagnostics = root.closest(".planning-workspace-shell")?.querySelector(".planning-advanced-diagnostics");
    if (diagnostics) diagnostics.hidden = !state.payload.permissions.diagnostics;
  } catch (error) {
    if (sequence !== loadSequence) return;
    root.innerHTML = '<section class="planning-ops-error" role="alert"><h2>Planning non disponibile</h2><p data-planning-error></p><button type="button" data-planning-retry>Riprova</button></section>';
    root.querySelector("[data-planning-error]").textContent = userMessageForError(
      error,
      "Non è stato possibile caricare il Planning. Riprova.",
    );
  } finally {
    if (sequence === loadSequence) root.setAttribute("aria-busy", "false");
  }
}

function refreshRoutes() {
  renderRouteList(root, filteredRoutes(state), state.payload.permissions.write);
}

async function selectOperationalDate(operationDate) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(operationDate || ""))) return;
  state.query = "";
  state.filter = "all";
  state.weekError = null;
  resetForecastEditor();
  syncDateUrl(operationDate);
  await load(operationDate);
  document.dispatchEvent(new CustomEvent("planning:date-changed", {
    detail: { operationDate },
  }));
}

async function loadWeekSummary() {
  const requestedWeek = operationalWeek(state.selectedOperationalDate);
  const missingDates = requestedWeek.filter((date) => !state.weekPayloads.has(date));
  if (!missingDates.length || state.weekLoading) return;
  state.weekLoading = true;
  state.weekError = null;
  renderCurrent();
  try {
    const payloads = await Promise.all(
      missingDates.map((operationDate) => planningOperationsApi.load({ operationDate })),
    );
    payloads.forEach((payload) => state.weekPayloads.set(payload.operation_date, payload));
  } catch (error) {
    state.weekError = userMessageForError(
      error,
      "Impossibile caricare il riepilogo settimanale.",
    );
  } finally {
    state.weekLoading = false;
    renderCurrent();
  }
}

async function assignmentChange(input, kind) {
  const assignmentId = Number(input.dataset[kind === "driver" ? "assignmentDriver" : "assignmentVehicle"]);
  const value = input.value.trim();
  const payload = kind === "driver"
    ? { driver_name: value, remove_driver: !value, actor: "web_operator" }
    : { plate: value, remove_vehicle: !value, actor: "web_operator" };
  try { await planningOperationsApi.assign(assignmentId, payload); await load(); }
  catch (error) { input.setCustomValidity(error?.message || "Assegnazione non valida."); input.reportValidity(); }
}

async function convocationChange(select) {
  const assignmentId = Number(select.dataset.convocationStatus);
  const route = state.payload.routes.find((item) => item.id === assignmentId);
  await planningOperationsApi.convocation(state.payload.planning.id, assignmentId, {
    status: select.value,
    scheduled_time: root.querySelector(`[data-convocation-time="${assignmentId}"]`)?.value || route?.convocation?.scheduled_time || null,
  });
  await load();
}

function handleInput(event) {
  if (event.target.matches("[data-manual-coverage-input]")) {
    const key = event.target.dataset.manualCoverageInput;
    state.forecastEditor.draft[key] = event.target.value;
    state.forecastEditor.error = null;
    const output = root.querySelector(`[data-manual-coverage-preview="${key}"]`);
    if (output) output.textContent = requirementPreview(event.target.value) ?? "—";
    return;
  }
  if (event.target.matches("[data-planning-query]")) {
    state.query = event.target.value;
    refreshRoutes();
  }
}

async function handleSubmit(event) {
  if (!event.target.matches("[data-planning-forecast-form]")) return;
  event.preventDefault();
  if (state.forecastEditor.saving) return;
  const { requirements, clearedExisting } = changedRequirements(
    state.forecastEditor,
  );
  if (clearedExisting) {
    state.forecastEditor.error = "La rimozione del valore manuale non è disponibile in questa versione.";
    renderCurrent();
    return;
  }
  if (!requirements.length) {
    state.forecastEditor.error = "Nessuna modifica da salvare.";
    renderCurrent();
    return;
  }
  state.forecastEditor.saving = true;
  state.forecastEditor.error = null;
  renderCurrent();
  try {
    await planningOperationsApi.saveForecast(state.selectedOperationalDate, {
      expected_fingerprint: state.payload.coverage.fingerprint,
      requirements,
    });
    resetForecastEditor();
    await load(state.selectedOperationalDate);
  } catch (error) {
    state.forecastEditor.saving = false;
    state.forecastEditor.error = error?.status === 409
      ? "Il fabbisogno è cambiato. Aggiorna i dati e riprova."
      : userMessageForError(error, "Impossibile salvare il fabbisogno.");
    renderCurrent();
  }
}

async function handleChange(event) {
  const target = event.target;
  if (target.matches("[data-planning-operation-date]")) {
    await selectOperationalDate(target.value);
    return;
  }
  if (target.matches("[data-planning-filter-select]")) { state.filter = target.value; refreshRoutes(); return; }
  if (target.matches("[data-assignment-driver]")) await assignmentChange(target, "driver");
  if (target.matches("[data-assignment-vehicle]")) await assignmentChange(target, "vehicle");
  if (target.matches("[data-convocation-status]")) await convocationChange(target);
  if (target.matches("[data-planning-import-file]") && target.files?.[0]) {
    const feedback = root.querySelector("[data-planning-import-feedback]");
    feedback.textContent = "Analisi del file in corso…";
    try {
      const preview = await planningOperationsApi.previewImport(target.files[0]);
      if (!preview.import_allowed) throw new Error(preview.blocking_reasons?.[0]?.message || "File non importabile.");
      const accepted = globalThis.confirm(`Anteprima valida: ${preview.total_rows} rotte, ${preview.warnings?.length || 0} avvisi. Confermare l'import?`);
      if (!accepted) { feedback.textContent = "Import annullato."; return; }
      const imported = await planningOperationsApi.importRoutes(target.files[0]);
      await planningOperationsApi.generate({ planning_import_id: imported.import_id });
      feedback.textContent = `${imported.rows_imported} rotte importate.`;
      await load();
    } catch (error) {
      feedback.textContent = error?.message || "Import non riuscito.";
    }
  }
}

function openWorkforcePlanning() {
  const onViewChanged = (event) => {
    if (event.detail?.view !== "workforce") return;
    document.removeEventListener("workspace:view-changed", onViewChanged);
    document.dispatchEvent(new CustomEvent("workforce:open-date", {
      detail: { operationDate: state.selectedOperationalDate },
    }));
  };
  document.addEventListener("workspace:view-changed", onViewChanged);
  document.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: { view: "workforce" },
  }));
}

function openFleet() {
  document.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: { view: "fleet" },
  }));
}

async function handleClick(event) {
  if (event.target.closest("[data-open-planning-forecast]")) { openForecastEditor(); return; }
  if (event.target.closest("[data-close-planning-forecast]")) { closeForecastEditor(); return; }
  if (event.target.closest("[data-open-workforce-planning]")) { openWorkforcePlanning(); return; }
  if (event.target.closest("[data-open-fleet]")) { openFleet(); return; }
  const selectedDay = event.target.closest("[data-planning-select-date]");
  if (selectedDay) { await selectOperationalDate(selectedDay.dataset.planningSelectDate); return; }
  const dayJump = event.target.closest("[data-planning-day-jump]");
  if (dayJump) {
    const targetDate = dayJump.dataset.planningDayJump === "today"
      ? todayOperationalDate()
      : addOperationalDays(
        state.selectedOperationalDate,
        dayJump.dataset.planningDayJump === "previous" ? -1 : 1,
      );
    await selectOperationalDate(targetDate);
    return;
  }
  if (event.target.closest("[data-load-planning-week]")) { await loadWeekSummary(); return; }
  const filter = event.target.closest("[data-planning-filter]");
  if (filter) { state.filter = filter.dataset.planningFilter; refreshRoutes(); return; }
  if (event.target.closest("[data-planning-retry]")) { await load(); return; }
  const lifecycle = event.target.closest("[data-planning-lifecycle]");
  if (lifecycle) { await planningOperationsApi.transition(state.payload.planning.id, lifecycle.dataset.planningLifecycle); await load(); }
}

export function initPlanningOperations(element) {
  root = element;
  if (!root) return Promise.resolve();
  if (root.dataset.planningOperationsInitialized === "true") {
    return initialLoadPromise || Promise.resolve();
  }
  root.dataset.planningOperationsInitialized = "true";
  root.addEventListener("input", handleInput);
  root.addEventListener("change", handleChange);
  root.addEventListener("click", handleClick);
  root.addEventListener("submit", handleSubmit);
  renderOperationsLoading(root);
  const requested = new URL(window.location.href).searchParams.get("planning_date");
  state.selectedOperationalDate = /^\d{4}-\d{2}-\d{2}$/.test(requested || "")
    ? requested
    : todayOperationalDate();
  initialLoadPromise = load(state.selectedOperationalDate);
  return initialLoadPromise;
}

export async function openPlanningOperationsDate(operationDate) {
  if (!root || !/^\d{4}-\d{2}-\d{2}$/.test(String(operationDate || ""))) return false;
  await selectOperationalDate(operationDate);
  return true;
}

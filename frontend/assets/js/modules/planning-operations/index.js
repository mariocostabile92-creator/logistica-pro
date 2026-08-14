import { planningOperationsApi } from "./api.js";
import { renderOperations, renderOperationsLoading, renderRouteList } from "./renderer.js?v=bridge1";
import { filteredRoutes, planningOperationsState as state } from "./state.js";
import { userMessageForError } from "../../utils/errors.js";

let root;
let initialLoadPromise = null;
let loadSequence = 0;

function today() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function syncDateUrl(operationDate) {
  const url = new URL(window.location.href);
  url.searchParams.set("planning_date", operationDate);
  history.replaceState(history.state, "", url);
}

async function load(operationDate = state.operationDate || today()) {
  const sequence = ++loadSequence;
  state.operationDate = operationDate;
  root.setAttribute("aria-busy", "true");
  try {
    const payload = await planningOperationsApi.load({ operationDate });
    if (sequence !== loadSequence) return;
    state.payload = payload;
    state.operationDate = payload.operation_date;
    renderOperations(root, state.payload, filteredRoutes(state));
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
  if (event.target.matches("[data-planning-query]")) {
    state.query = event.target.value;
    refreshRoutes();
  }
}

async function handleChange(event) {
  const target = event.target;
  if (target.matches("[data-planning-operation-date]")) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(target.value)) return;
    state.query = "";
    state.filter = "all";
    syncDateUrl(target.value);
    await load(target.value);
    document.dispatchEvent(new CustomEvent("planning:date-changed", { detail: { operationDate: target.value } }));
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
      detail: { operationDate: state.operationDate },
    }));
  };
  document.addEventListener("workspace:view-changed", onViewChanged);
  document.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: { view: "workforce" },
  }));
}

async function handleClick(event) {
  if (event.target.closest("[data-open-workforce-planning]")) { openWorkforcePlanning(); return; }
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
  renderOperationsLoading(root);
  const requested = new URL(window.location.href).searchParams.get("planning_date");
  state.operationDate = /^\d{4}-\d{2}-\d{2}$/.test(requested || "") ? requested : today();
  initialLoadPromise = load(state.operationDate);
  return initialLoadPromise;
}

export async function openPlanningOperationsDate(operationDate) {
  if (!root || !/^\d{4}-\d{2}-\d{2}$/.test(String(operationDate || ""))) return false;
  syncDateUrl(operationDate);
  await load(operationDate);
  return true;
}

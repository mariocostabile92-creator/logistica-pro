import { planningOperationsApi } from "./api.js";
import { renderOperations, renderOperationsLoading, renderRouteList } from "./renderer.js?v=brand2";
import { filteredRoutes, planningOperationsState as state } from "./state.js";
import { userMessageForError } from "../../utils/errors.js";

let root;
let initialLoadPromise = null;
async function load() {
  root.setAttribute("aria-busy", "true");
  try {
    state.payload = await planningOperationsApi.load({});
    renderOperations(root, state.payload, filteredRoutes(state));
    const diagnostics = root.closest(".planning-workspace-shell")?.querySelector(".planning-advanced-diagnostics");
    if (diagnostics) diagnostics.hidden = !state.payload.permissions.diagnostics;
  } catch (error) {
    root.innerHTML = '<section class="planning-ops-error" role="alert"><h2>Planning non disponibile</h2><p data-planning-error></p><button type="button" data-planning-retry>Riprova</button></section>';
    root.querySelector("[data-planning-error]").textContent = userMessageForError(
      error,
      "Non è stato possibile caricare il Planning. Riprova.",
    );
  } finally {
    root.setAttribute("aria-busy", "false");
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

async function handleClick(event) {
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
  initialLoadPromise = load();
  return initialLoadPromise;
}

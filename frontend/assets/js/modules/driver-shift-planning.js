import {
  addSource,
  createPlanning,
  getMergePreview,
  listPlannings,
  removeSource,
  resolveImport,
  replaceSources,
} from "./driver-shift-planning-api.js";
import {
  renderMergeRows,
  renderMergeSummary,
  renderPagination,
  renderPlanningHeader,
  renderPlanningSelector,
  renderSources,
} from "./driver-shift-planning-presenter.js";
import { createDriverShiftPlanningState } from "./driver-shift-planning-state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";


const FILTERS = new Set([
  "", "DISTINCT_ASSIGNMENT", "EXACT_DUPLICATE", "POTENTIAL_CONFLICT",
  "IDENTITY_CONFLICT", "UNRESOLVED_IDENTITY",
]);


function presentError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
  return presentation.message;
}


export function initDriverShiftPlanning({ openImport, onChanged = () => {} }) {
  const store = createDriverShiftPlanningState();
  const { state } = store;
  let initialized = false;
  let searchTimer = null;
  let sourceToRemove = null;

  const elements = {};

  function bindElements() {
    Object.assign(elements, {
      section: byId("driverShiftPlanningSection"),
      state: byId("driverShiftPlanningState"),
      workspace: byId("driverShiftPlanningWorkspace"),
      header: byId("driverShiftPlanningHeader"),
      selectorWrap: byId("driverShiftPlanningSelectorWrap"),
      selector: byId("driverShiftPlanningSelector"),
      sources: byId("driverShiftPlanningSources"),
      summary: byId("driverShiftMergeSummary"),
      rows: byId("driverShiftMergeRows"),
      search: byId("driverShiftMergeSearch"),
      previous: byId("driverShiftPrevious"),
      next: byId("driverShiftNext"),
      pagination: byId("driverShiftPaginationStatus"),
      createDialog: byId("driverShiftPlanningDialog"),
      createForm: byId("driverShiftPlanningForm"),
      replaceDialog: byId("driverShiftReplaceDialog"),
      removeDialog: byId("driverShiftRemoveDialog"),
    });
  }

  function renderFilters() {
    document.querySelectorAll("[data-driver-shift-filter]").forEach((button) => {
      const active = button.dataset.driverShiftFilter === state.classification;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function render() {
    elements.section.hidden = false;
    const hasPlanning = Boolean(state.planning);
    byId("driverShiftReplaceSourcesBtn").disabled = !hasPlanning;
    byId("driverShiftAddSourceBtn").disabled = hasPlanning && state.planning.status !== "DRAFT";
    elements.state.hidden = hasPlanning;
    elements.workspace.hidden = !hasPlanning;
    if (!hasPlanning) {
      elements.state.innerHTML = `
        <div>
          <strong>Crea il Planning turni</strong>
          <p>Definisci il periodo oppure importa il primo file per usare il range rilevato come suggerimento.</p>
        </div>
        <div class="driver-shift-empty-actions">
          <button type="button" class="secondary" data-create-driver-shift-planning>Crea planning</button>
          <button type="button" data-add-first-driver-shift-source>Aggiungi file turni</button>
        </div>
      `;
      elements.state.querySelector("[data-create-driver-shift-planning]")
        .addEventListener("click", () => openCreateDialog());
      elements.state.querySelector("[data-add-first-driver-shift-source]")
        .addEventListener("click", () => startImport("add"));
      return;
    }

    renderPlanningSelector(elements.selector, state.plannings, state.planning.id);
    elements.selectorWrap.hidden = state.plannings.length <= 1;
    renderPlanningHeader(
      elements.header,
      state.preview?.planning || state.planning,
      state.preview?.sources?.length || 0,
    );
    renderSources(elements.sources, state.preview?.sources || []);
    if (state.planning.status !== "DRAFT") {
      byId("driverShiftReplaceSourcesBtn").disabled = true;
      elements.sources.querySelectorAll("[data-remove-driver-shift-source]")
        .forEach((button) => { button.disabled = true; });
    }
    if (state.preview) {
      renderMergeSummary(elements.summary, state.preview.summary);
      renderMergeRows(elements.rows, state.preview);
      renderPagination({
        previous: elements.previous,
        next: elements.next,
        status: elements.pagination,
      }, state.preview);
    }
    renderFilters();
  }

  async function refresh(preferredPlanningId = null) {
    const request = store.beginRequest();
    elements.section.hidden = false;
    elements.section.setAttribute("aria-busy", "true");
    try {
      const collection = await listPlannings();
      if (!store.isCurrent(request)) return;
      state.plannings = collection.items;
      state.planning = state.plannings.find((item) => item.id === preferredPlanningId)
        || collection.current
        || null;
      state.preview = state.planning
        ? await getMergePreview(state.planning.id, state)
        : null;
      if (!store.completeRequest(request)) return;
      render();
    } catch (error) {
      if (!store.completeRequest(request)) return;
      presentError("workforce.driver-shift-planning", error);
      elements.section.hidden = false;
      elements.state.hidden = false;
      elements.workspace.hidden = true;
      elements.state.innerHTML = `
        <strong>Fonti turni non disponibili.</strong>
        <button type="button" class="secondary" data-retry-driver-shift>Riprova</button>
      `;
      elements.state.querySelector("[data-retry-driver-shift]")
        .addEventListener("click", () => refresh(preferredPlanningId));
    } finally {
      elements.section.setAttribute("aria-busy", "false");
    }
  }

  async function refreshPreview({ resetPaging = false } = {}) {
    if (!state.planning) return;
    if (resetPaging) store.resetPaging();
    const request = store.beginRequest();
    elements.rows.setAttribute("aria-busy", "true");
    try {
      const preview = await getMergePreview(state.planning.id, state);
      if (!store.completeRequest(request)) return;
      state.preview = preview;
      state.planning = preview.planning;
      render();
    } catch (error) {
      if (!store.completeRequest(request)) return;
      presentError("workforce.driver-shift-preview", error);
    } finally {
      elements.rows.setAttribute("aria-busy", "false");
    }
  }

  function openCreateDialog(suggestion = null) {
    byId("driverShiftPlanningLabel").value = "";
    byId("driverShiftPlanningStart").value = suggestion?.date_from || "";
    byId("driverShiftPlanningEnd").value = suggestion?.date_to || "";
    elements.createDialog.showModal();
    byId("driverShiftPlanningLabel").focus();
  }

  function startImport(mode) {
    state.pendingImportMode = mode;
    openImport();
  }

  async function handleImported(result, preview) {
    const mode = state.pendingImportMode;
    if (!mode) return false;
    let importId = null;
    try {
      const reference = await resolveImport(result.fingerprint || "");
      importId = Number(reference.workforce_import_id);
    } catch (error) {
      presentError("workforce.driver-shift-import-reference", error);
      state.pendingImportMode = null;
      return false;
    }
    if (!Number.isInteger(importId) || importId <= 0) {
      setMessage("Import completato, ma il collegamento alla fonte non è disponibile.", "warning");
      state.pendingImportMode = null;
      return false;
    }
    if (!state.planning) {
      state.pendingImport = { importId, preview, mode };
      openCreateDialog(preview);
      return true;
    }
    try {
      if (mode === "replace") await replaceSources(state.planning.id, [importId]);
      else await addSource(state.planning.id, importId);
      state.pendingImportMode = null;
      await refresh(state.planning.id);
      onChanged();
      return true;
    } catch (error) {
      presentError("workforce.driver-shift-source", error);
      return false;
    }
  }

  async function submitPlanning(event) {
    event.preventDefault();
    const submit = event.submitter || byId("driverShiftPlanningSave");
    const periodStart = byId("driverShiftPlanningStart").value;
    const periodEnd = byId("driverShiftPlanningEnd").value;
    const suggested = state.pendingImport?.preview;
    if (
      suggested?.date_from
      && suggested?.date_to
      && (suggested.date_to < periodStart || suggested.date_from > periodEnd)
    ) {
      setMessage(
        "Il periodo del file non coincide con il Planning turni selezionato.",
        "warning",
      );
      return;
    }
    setLoading(submit, true, "Creazione...");
    try {
      const planning = await createPlanning({
        label: byId("driverShiftPlanningLabel").value.trim() || null,
        period_start: periodStart,
        period_end: periodEnd,
      });
      if (state.pendingImport) {
        if (state.pendingImport.mode === "replace") {
          await replaceSources(planning.id, [state.pendingImport.importId]);
        } else {
          await addSource(planning.id, state.pendingImport.importId);
        }
      }
      state.pendingImport = null;
      state.pendingImportMode = null;
      elements.createDialog.close();
      await refresh(planning.id);
      onChanged();
    } catch (error) {
      presentError("workforce.driver-shift-create", error);
    } finally {
      setLoading(submit, false);
    }
  }

  function requestRemove(sourceId) {
    sourceToRemove = sourceId;
    elements.removeDialog.showModal();
    byId("driverShiftRemoveConfirm").focus();
  }

  async function confirmRemove() {
    if (!state.planning || !sourceToRemove) return;
    const button = byId("driverShiftRemoveConfirm");
    setLoading(button, true, "Rimozione...");
    try {
      await removeSource(state.planning.id, sourceToRemove);
      sourceToRemove = null;
      elements.removeDialog.close();
      await refresh(state.planning.id);
      onChanged();
    } catch (error) {
      presentError("workforce.driver-shift-remove", error);
    } finally {
      setLoading(button, false);
    }
  }

  function bindEvents() {
    byId("driverShiftCreateBtn").addEventListener("click", () => openCreateDialog());
    byId("driverShiftAddSourceBtn").addEventListener("click", () => startImport("add"));
    byId("driverShiftReplaceSourcesBtn").addEventListener("click", () => {
      elements.replaceDialog.showModal();
    });
    byId("driverShiftReplaceCancel").addEventListener("click", () => elements.replaceDialog.close());
    byId("driverShiftReplaceConfirm").addEventListener("click", () => {
      elements.replaceDialog.close();
      startImport("replace");
    });
    byId("driverShiftPlanningCancel").addEventListener("click", () => {
      elements.createDialog.close();
      state.pendingImport = null;
      state.pendingImportMode = null;
    });
    elements.createForm.addEventListener("submit", submitPlanning);
    elements.selector.addEventListener("change", () => {
      state.classification = "";
      state.search = "";
      elements.search.value = "";
      store.resetPaging();
      refresh(Number(elements.selector.value));
    });
    elements.sources.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-driver-shift-source]");
      if (button) requestRemove(Number(button.dataset.removeDriverShiftSource));
    });
    byId("driverShiftRemoveCancel").addEventListener("click", () => {
      sourceToRemove = null;
      elements.removeDialog.close();
    });
    byId("driverShiftRemoveConfirm").addEventListener("click", confirmRemove);
    document.querySelectorAll("[data-driver-shift-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.driverShiftFilter;
        if (!FILTERS.has(value)) return;
        state.classification = value;
        refreshPreview({ resetPaging: true });
      });
    });
    elements.search.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        state.search = elements.search.value.trim();
        refreshPreview({ resetPaging: true });
      }, 250);
    });
    elements.previous.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      refreshPreview();
    });
    elements.next.addEventListener("click", () => {
      state.offset += state.limit;
      refreshPreview();
    });
  }

  function init() {
    if (initialized) return;
    initialized = true;
    bindElements();
    bindEvents();
  }

  function reset() {
    store.reset();
    render();
  }

  init();
  return { refresh, refreshPreview, handleImported, reset };
}

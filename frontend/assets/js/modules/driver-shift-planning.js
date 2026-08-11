import {
  addSource,
  createPlanning,
  getMergePreview,
  listPlannings,
  removeSource,
  resolveImport,
  replaceSources,
  resolveConflict,
  publishPlanning,
  createRevision,
  listWorkforceMembers,
} from "./driver-shift-planning-api.js?v=2";
import {
  renderMergeRows,
  renderMergeSummary,
  renderPagination,
  renderPlanningHeader,
  renderPlanningSelector,
  renderSources,
} from "./driver-shift-planning-presenter.js?v=3";
import { createDriverShiftPlanningState } from "./driver-shift-planning-state.js?v=2";
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
      draftNotice: byId("driverShiftDraftNotice"),
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
      publishDialog: byId("driverShiftPublishDialog"),
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
      byId("driverShiftResolveBtn").hidden = true;
      byId("driverShiftPublishBtn").hidden = true;
      byId("driverShiftRevisionBtn").hidden = true;
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
    const isDraft = state.planning.status === "DRAFT";
    elements.draftNotice.hidden = !isDraft;
    const blockers = Number(state.preview?.summary?.conflicts_to_resolve || 0);
    const resolveButton = byId("driverShiftResolveBtn");
    const publishButton = byId("driverShiftPublishBtn");
    const revisionButton = byId("driverShiftRevisionBtn");
    resolveButton.hidden = !isDraft || blockers === 0;
    publishButton.hidden = !isDraft;
    publishButton.disabled = !state.preview?.summary?.ready_to_publish;
    revisionButton.hidden = state.planning.status !== "ACTIVE";
    if (state.planning.status !== "DRAFT") {
      byId("driverShiftReplaceSourcesBtn").disabled = true;
      elements.sources.querySelectorAll("[data-remove-driver-shift-source]")
        .forEach((button) => { button.disabled = true; });
    }
    if (state.preview) {
      renderMergeSummary(elements.summary, state.preview.summary);
      renderMergeRows(elements.rows, state.preview, state.members);
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
      const [collection, memberCollection] = await Promise.all([
        listPlannings(),
        listWorkforceMembers(),
      ]);
      if (!store.isCurrent(request)) return;
      state.plannings = collection.items;
      state.members = Array.isArray(memberCollection)
        ? memberCollection
        : (memberCollection.items || []);
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

  async function saveResolution(conflictKey, resolutionType, sourceRowId = null, memberId = null) {
    if (!state.planning) return;
    try {
      await resolveConflict(state.planning.id, conflictKey, {
        expected_version: state.planning.version,
        resolution_type: resolutionType,
        selected_source_row_id: sourceRowId,
        workforce_member_id: memberId,
      });
      await refreshPreview();
    } catch (error) {
      if (error?.status === 409) setMessage("Il planning è cambiato. Preview ricaricata.", "warning");
      else presentError("workforce.driver-shift-resolution", error);
      await refreshPreview();
    }
  }

  function openPublishDialog() {
    if (!state.preview?.summary?.ready_to_publish) return;
    const planning = state.planning;
    byId("driverShiftPublishSummary").innerHTML = `
      <dl class="driver-shift-publish-summary">
        <div><dt>Periodo</dt><dd>${planning.period_start} → ${planning.period_end}</dd></div>
        <div><dt>Giornate unificate</dt><dd>${state.preview.summary.unified_rows}</dd></div>
        <div><dt>Fonti</dt><dd>${state.preview.sources.length}</dd></div>
      </dl>
    `;
    elements.publishDialog.showModal();
    byId("driverShiftPublishConfirm").focus();
  }

  async function confirmPublish() {
    if (!state.planning || !state.preview) return;
    const button = byId("driverShiftPublishConfirm");
    setLoading(button, true, "Pubblicazione...");
    try {
      await publishPlanning(state.planning.id, {
        expected_version: state.planning.version,
        expected_preview_fingerprint: state.preview.preview_fingerprint,
      });
      elements.publishDialog.close();
      await refresh(state.planning.id);
      await onChanged({
        type: "published",
        planningId: state.planning.id,
        periodStart: state.planning.period_start,
      });
      setMessage("Turni unificati pubblicati in Workforce.", "success");
    } catch (error) {
      if (error?.status === 409) {
        setMessage("La preview è cambiata. Controllala prima di pubblicare.", "warning");
        elements.publishDialog.close();
        await refreshPreview();
      } else {
        presentError("workforce.driver-shift-publish", error);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function createNewRevision() {
    if (!state.planning) return;
    const button = byId("driverShiftRevisionBtn");
    setLoading(button, true, "Creazione...");
    try {
      const revision = await createRevision(state.planning.id);
      await refresh(revision.id);
    } catch (error) {
      presentError("workforce.driver-shift-revision", error);
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
    byId("driverShiftResolveBtn").addEventListener("click", () => {
      const summary = state.preview?.summary || {};
      state.classification = summary.potential_conflicts > 0
        ? "POTENTIAL_CONFLICT"
        : summary.identity_conflicts > 0 ? "IDENTITY_CONFLICT" : "UNRESOLVED_IDENTITY";
      refreshPreview({ resetPaging: true });
      elements.rows.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    byId("driverShiftPublishBtn").addEventListener("click", openPublishDialog);
    byId("driverShiftPublishCancel").addEventListener("click", () => elements.publishDialog.close());
    byId("driverShiftPublishConfirm").addEventListener("click", confirmPublish);
    byId("driverShiftRevisionBtn").addEventListener("click", createNewRevision);
    elements.rows.addEventListener("click", (event) => {
      const choose = event.target.closest("[data-resolve-conflict]");
      if (choose) {
        saveResolution(choose.dataset.resolveConflict, "USE_SOURCE_ROW", Number(choose.dataset.sourceRowId));
        return;
      }
      const exclude = event.target.closest("[data-exclude-conflict]");
      if (exclude) {
        saveResolution(exclude.dataset.excludeConflict, "EXCLUDE");
        return;
      }
      const unresolved = event.target.closest("[data-resolve-unresolved]");
      if (unresolved) {
        const card = unresolved.closest(".driver-shift-row");
        const memberId = Number(card.querySelector("[data-unresolved-member]")?.value);
        if (!memberId) {
          setMessage("Seleziona il driver Workforce da associare.", "warning");
          return;
        }
        saveResolution(
          unresolved.dataset.resolveUnresolved,
          "USE_SOURCE_ROW",
          Number(unresolved.dataset.sourceRowId),
          memberId,
        );
      }
    });
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

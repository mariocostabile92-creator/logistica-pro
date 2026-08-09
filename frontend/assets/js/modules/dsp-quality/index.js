import { can } from "../../auth/state.js";
import {
  deleteTransporterMapping,
  getLatestQualityDrivers,
  getLatestQualityMetrics,
  getLatestQualityScorecard,
  getTransporterMappingHistory,
  getTransporterReconciliation,
  importQualityScorecard,
  previewQualityScorecard,
  putTransporterMapping,
  searchQualityWorkforceCandidates,
} from "./api.js?v=5";
import { qualityErrorMessage, validateQualityFile } from "./import.js";
import { renderDspQuality } from "./presenter.js?v=6";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "./state.js?v=5";


let initialized = false;
let root = null;
let state = createDspQualityState();
let requestVersion = 0;
let requestController = null;
let latestRequestVersion = 0;
let latestRequestController = null;
let metricsRequestVersion = 0;
let metricsRequestController = null;
let driversRequestVersion = 0;
let driversRequestController = null;
let reconciliationRequestController = null;
let candidateRequestController = null;
let candidateTimer = null;


function commit(event) {
  state = applyDspQualityEvent(state, event);
  renderDspQuality(root, deriveDspQualityView(state));
}


async function loadLatest({ notice = null } = {}) {
  const version = ++latestRequestVersion;
  latestRequestController?.abort();
  latestRequestController = new AbortController();
  commit({ type: "latest-started" });
  try {
    const latest = await getLatestQualityScorecard({
      signal: latestRequestController.signal,
    });
    if (version === latestRequestVersion) {
      commit({ type: "latest-completed", latest, notice });
    }
    return latest;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    if (version === latestRequestVersion) {
      commit({
        type: "latest-failed",
        message: "Impossibile caricare l'ultima scorecard. Riprova.",
      });
    }
    return null;
  }
}


async function loadMetrics({ force = false } = {}) {
  if (!force && ["loading", "available"].includes(state.metrics?.phase)) return;
  const version = ++metricsRequestVersion;
  metricsRequestController?.abort();
  metricsRequestController = new AbortController();
  commit({ type: "metrics-started" });
  try {
    const data = await getLatestQualityMetrics({ signal: metricsRequestController.signal });
    if (version === metricsRequestVersion) commit({ type: "metrics-completed", data });
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (version === metricsRequestVersion) {
      commit({ type: "metrics-failed", message: "Impossibile caricare le metriche. Riprova." });
    }
  }
}


async function loadDrivers({ force = false } = {}) {
  if (!force && ["loading", "available"].includes(state.drivers?.phase)) return;
  const version = ++driversRequestVersion;
  driversRequestController?.abort();
  driversRequestController = new AbortController();
  commit({ type: "drivers-started" });
  try {
    const data = await getLatestQualityDrivers({ signal: driversRequestController.signal });
    if (version === driversRequestVersion) commit({ type: "drivers-completed", data });
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (version === driversRequestVersion) {
      commit({ type: "drivers-failed", message: "Impossibile caricare le performance driver. Riprova." });
    }
  }
}


function activeReconciliationRow() {
  const reconciliation = state.drivers?.reconciliation || {};
  return (reconciliation.data?.rows || []).find(
    row => row.transporter_external_id === reconciliation.activeExternalId,
  ) || null;
}


function nextUnmapped(data, currentExternalId) {
  const rows = data?.rows || [];
  const currentIndex = rows.findIndex(
    row => row.transporter_external_id === currentExternalId,
  );
  return [
    ...rows.slice(currentIndex + 1),
    ...rows.slice(0, Math.max(currentIndex, 0)),
  ].find(row => row.mapping_status === "UNMAPPED")?.transporter_external_id || null;
}


async function loadMappingHistory(externalId) {
  if (!externalId) return;
  try {
    const result = await getTransporterMappingHistory(externalId);
    if (state.drivers?.reconciliation?.activeExternalId === externalId) {
      commit({ type: "history-completed", items: result.items || [] });
    }
  } catch {
    commit({ type: "history-completed", items: [] });
  }
}


async function loadReconciliation({ keepFilter = false, advanceAfter = null } = {}) {
  reconciliationRequestController?.abort();
  reconciliationRequestController = new AbortController();
  commit({ type: "reconciliation-started" });
  try {
    const data = await getTransporterReconciliation({
      signal: reconciliationRequestController.signal,
    });
    const activeExternalId = advanceAfter ? nextUnmapped(data, advanceAfter) : undefined;
    commit({
      type: "reconciliation-completed",
      data,
      activeExternalId,
      setActive: Boolean(advanceAfter),
      keepFilter,
    });
    if (activeExternalId) void loadMappingHistory(activeExternalId);
    return data;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    commit({
      type: "reconciliation-failed",
      message: "Impossibile caricare le associazioni Transporter.",
    });
    return null;
  }
}


async function openReconciliation(externalId = null) {
  commit({ type: "reconciliation-opened" });
  const data = await loadReconciliation();
  if (data && externalId) {
    commit({ type: "reconciliation-row-opened", externalId });
    void loadMappingHistory(externalId);
  }
}


async function loadCandidates(query) {
  candidateRequestController?.abort();
  if (query.trim().length < 2) return;
  candidateRequestController = new AbortController();
  try {
    const result = await searchQualityWorkforceCandidates(query, {
      signal: candidateRequestController.signal,
    });
    if (state.drivers?.reconciliation?.candidateSearch === query) {
      commit({ type: "candidates-completed", items: result.items || [] });
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({ type: "candidates-failed", message: "Ricerca Workforce non disponibile." });
  }
}


function mappingErrorMessage(error) {
  return typeof error?.detail === "string"
    ? error.detail
    : "Impossibile salvare l'associazione. Riprova.";
}


async function confirmMapping() {
  const reconciliation = state.drivers?.reconciliation || {};
  const row = activeReconciliationRow();
  const candidate = reconciliation.selectedCandidate;
  if (!row || !candidate || reconciliation.mutationPhase === "loading") return;
  commit({ type: "mapping-started" });
  try {
    await putTransporterMapping(row.transporter_external_id, {
      workforce_member_id: candidate.workforce_member_id,
      expected_updated_at: row.updated_at || null,
    });
    await Promise.all([
      loadDrivers({ force: true }),
      loadReconciliation({ keepFilter: true, advanceAfter: row.transporter_external_id }),
    ]);
    requestAnimationFrame(() => root.querySelector("[data-quality-candidate-search]")?.focus());
  } catch (error) {
    commit({
      type: error?.status === 409 ? "mapping-conflict" : "mapping-failed",
      message: error?.status === 409
        ? "Associazione aggiornata da un altro utente. Chiudi e riapri per continuare."
        : mappingErrorMessage(error),
    });
  }
}


async function removeMapping() {
  const reconciliation = state.drivers?.reconciliation || {};
  const row = activeReconciliationRow();
  if (!row?.updated_at || reconciliation.mutationPhase === "loading") return;
  commit({ type: "mapping-started" });
  try {
    await deleteTransporterMapping(row.transporter_external_id, row.updated_at);
    await Promise.all([
      loadDrivers({ force: true }),
      loadReconciliation({ keepFilter: true, advanceAfter: row.transporter_external_id }),
    ]);
  } catch (error) {
    commit({
      type: error?.status === 409 ? "mapping-conflict" : "mapping-failed",
      message: error?.status === 409
        ? "Associazione aggiornata da un altro utente. Chiudi e riapri per continuare."
        : mappingErrorMessage(error),
    });
  }
}


async function analyze(file) {
  const message = validateQualityFile(file);
  if (message) {
    commit({ type: "file-invalid", file, message });
    return;
  }
  const version = ++requestVersion;
  requestController?.abort();
  requestController = new AbortController();
  commit({ type: "preview-started", file });
  try {
    const preview = await previewQualityScorecard(file, { signal: requestController.signal });
    if (version === requestVersion) commit({ type: "preview-completed", preview });
  } catch (error) {
    const safeMessage = qualityErrorMessage(error, "preview");
    if (safeMessage && version === requestVersion) commit({ type: "preview-failed", message: safeMessage });
  }
}


async function confirmImport() {
  const view = deriveDspQualityView(state);
  if (!view.canConfirm) return;
  commit({ type: "import-started" });
  try {
    const result = await importQualityScorecard({
      file: state.file,
      previewToken: state.preview.preview_token,
      expectedAction: state.preview.idempotency?.action || null,
    });
    commit({ type: "import-completed", result });
    await loadLatest({ notice: "Scorecard importata" });
  } catch (error) {
    const message = qualityErrorMessage(error, "import");
    if (message) commit({ type: "import-failed", message });
  }
}


function selectedFile(input) {
  return input?.files?.[0] || null;
}


function bindEvents() {
  root.addEventListener("click", (event) => {
    if (event.target.closest("[data-quality-pick]")) root.querySelector("[data-quality-file]")?.click();
    if (event.target.closest("[data-quality-confirm]")) void confirmImport();
    if (event.target.closest("[data-quality-reset]")) commit({ type: "reset" });
    if (event.target.closest("[data-quality-import-open]")) commit({ type: "import-opened" });
    if (event.target.closest("[data-quality-back]")) commit({ type: "latest-restored" });
    if (event.target.closest("[data-quality-retry]")) void loadLatest();
    if (event.target.closest("[data-quality-metrics-retry]")) void loadMetrics({ force: true });
    if (event.target.closest("[data-quality-drivers-retry]")) void loadDrivers({ force: true });
    if (event.target.closest("[data-quality-reconciliation-open]")) void openReconciliation();
    if (event.target.closest("[data-quality-reconciliation-close]")) commit({ type: "reconciliation-closed" });
    if (event.target.closest("[data-quality-reconciliation-retry]")) void loadReconciliation();
    const reconciliationExternalId = event.target.closest("[data-quality-reconciliation-row]")?.dataset.qualityReconciliationRow;
    if (reconciliationExternalId) {
      if (!state.drivers?.reconciliation?.open) {
        void openReconciliation(reconciliationExternalId);
      } else {
        commit({ type: "reconciliation-row-opened", externalId: reconciliationExternalId });
        void loadMappingHistory(reconciliationExternalId);
        requestAnimationFrame(() => root.querySelector("[data-quality-candidate-search]")?.focus());
      }
    }
    if (event.target.closest("[data-quality-association-close]")) commit({ type: "reconciliation-row-closed" });
    const reconciliationFilter = event.target.closest("[data-quality-reconciliation-filter]")?.dataset.qualityReconciliationFilter;
    if (reconciliationFilter) commit({ type: "reconciliation-filter-changed", filter: reconciliationFilter });
    const candidateId = Number(event.target.closest("[data-quality-candidate-id]")?.dataset.qualityCandidateId);
    if (Number.isInteger(candidateId) && candidateId > 0) {
      const candidate = (state.drivers?.reconciliation?.candidates || []).find(
        item => item.workforce_member_id === candidateId,
      );
      if (candidate) commit({ type: "candidate-selected", candidate });
    }
    if (event.target.closest("[data-quality-mapping-confirm]")) void confirmMapping();
    if (event.target.closest("[data-quality-mapping-remove]")) void removeMapping();
    const metricFilter = event.target.closest("[data-quality-metrics-filter]")?.dataset.qualityMetricsFilter;
    if (metricFilter) commit({ type: "metrics-filter-changed", filter: metricFilter });
    const driverFilter = event.target.closest("[data-quality-drivers-filter]")?.dataset.qualityDriversFilter;
    if (driverFilter) commit({ type: "drivers-filter-changed", filter: driverFilter });
    const sortKey = event.target.closest("[data-quality-drivers-sort]")?.dataset.qualityDriversSort;
    if (sortKey) {
      const current = state.drivers.sort || {};
      commit({
        type: "drivers-sort-changed",
        sort: {
          key: sortKey,
          direction: current.key === sortKey && current.direction === "asc" ? "desc" : "asc",
        },
      });
    }
    const rowId = event.target.closest("[data-quality-driver-open]")?.dataset.qualityDriverOpen;
    if (rowId) commit({ type: "driver-opened", rowId });
    if (event.target.closest("[data-quality-driver-close]")) commit({ type: "driver-closed" });
    const workforceId = Number(event.target.closest("[data-quality-driver-workforce]")?.dataset.qualityDriverWorkforce);
    if (Number.isInteger(workforceId) && workforceId > 0) {
      document.dispatchEvent(new CustomEvent("workspace:navigate", {
        detail: { view: "workforce", driverId: workforceId },
      }));
    }
    if (event.target.closest("[data-quality-overview]")) commit({ type: "overview-opened" });
    const section = event.target.closest("[data-quality-section]")?.dataset.qualitySection;
    if (section) {
      commit({ type: "section-changed", section });
      if (section === "metrics") void loadMetrics();
      if (section === "drivers") void loadDrivers();
    }
  });
  root.addEventListener("change", (event) => {
    if (event.target.matches("[data-quality-file]")) void analyze(selectedFile(event.target));
  });
  root.addEventListener("input", (event) => {
    if (event.target.matches("[data-quality-metrics-search]")) {
      commit({ type: "metrics-search-changed", search: event.target.value });
      requestAnimationFrame(() => {
        const input = root.querySelector("[data-quality-metrics-search]");
        input?.focus();
        input?.setSelectionRange?.(state.metrics.search.length, state.metrics.search.length);
      });
    }
    if (event.target.matches("[data-quality-drivers-search]")) {
      commit({ type: "drivers-search-changed", search: event.target.value });
      requestAnimationFrame(() => {
        const input = root.querySelector("[data-quality-drivers-search]");
        input?.focus();
        input?.setSelectionRange?.(state.drivers.search.length, state.drivers.search.length);
      });
    }
    if (event.target.matches("[data-quality-reconciliation-search]")) {
      commit({ type: "reconciliation-search-changed", search: event.target.value });
      requestAnimationFrame(() => root.querySelector("[data-quality-reconciliation-search]")?.focus());
    }
    if (event.target.matches("[data-quality-candidate-search]")) {
      const query = event.target.value;
      commit({ type: "candidate-search-changed", search: query });
      clearTimeout(candidateTimer);
      candidateTimer = setTimeout(() => void loadCandidates(query), 250);
      requestAnimationFrame(() => root.querySelector("[data-quality-candidate-search]")?.focus());
    }
  });
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.drivers?.reconciliation?.activeExternalId) {
      event.preventDefault();
      commit({ type: "reconciliation-row-closed" });
      return;
    }
    if (event.key === "Escape" && state.drivers?.reconciliation?.open) {
      event.preventDefault();
      commit({ type: "reconciliation-closed" });
      return;
    }
    if (!event.target.matches("[data-quality-candidate-search]")) return;
    const candidates = state.drivers?.reconciliation?.candidates || [];
    if (event.key === "ArrowDown" && candidates.length) {
      event.preventDefault();
      root.querySelector("[data-quality-candidate-id]")?.focus();
    }
    if (event.key === "Enter" && candidates.length) {
      event.preventDefault();
      commit({ type: "candidate-selected", candidate: candidates[0] });
    }
  });
  root.addEventListener("dragover", (event) => {
    const zone = event.target.closest("[data-quality-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  root.addEventListener("dragleave", (event) => {
    event.target.closest("[data-quality-dropzone]")?.classList.remove("is-dragging");
  });
  root.addEventListener("drop", (event) => {
    const zone = event.target.closest("[data-quality-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("is-dragging");
    void analyze(event.dataTransfer?.files?.[0] || null);
  });
}


export function initDspQuality() {
  if (initialized) return;
  initialized = true;
  root = document.getElementById("dspQualityRoot");
  state = createDspQualityState({ canImport: can("admin:write") });
  bindEvents();
  renderDspQuality(root, deriveDspQualityView(state));
  void loadLatest();
}

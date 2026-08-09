import { can } from "../../auth/state.js";
import {
  applyExactTransporterIdentitySource,
  deleteTransporterMapping,
  getQualityDrivers,
  getQualityMetrics,
  getQualityScorecard,
  getQualityScorecardHistory,
  getTransporterMappingHistory,
  getTransporterReconciliation,
  importQualityScorecard,
  previewQualityScorecard,
  previewTransporterIdentitySource,
  putTransporterMapping,
  searchQualityWorkforceCandidates,
} from "./api.js?v=7";
import { qualityErrorMessage, validateQualityFile } from "./import.js";
import { validateIdentitySourceFile } from "./identity-source.js?v=2";
import { renderDspQuality } from "./presenter.js?v=10";
import { updateReconciliationCandidateRegion } from "./reconciliation-presenter.js?v=9";
import {
  currentSuggestion,
  isReviewShortcutTarget,
} from "./suggestion-review.js?v=1";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "./state.js?v=8";


let initialized = false;
let root = null;
let state = createDspQualityState();
let requestVersion = 0;
let requestController = null;
let latestRequestVersion = 0;
let latestRequestController = null;
let historyRequestVersion = 0;
let historyRequestController = null;
let metricsRequestVersion = 0;
let metricsRequestController = null;
let driversRequestVersion = 0;
let driversRequestController = null;
let reconciliationRequestController = null;
let candidateRequestController = null;
let candidateRequestVersion = 0;
let candidateTimer = null;
let identitySourceRequestController = null;
let reviewCandidateRequestController = null;
let reviewCandidateTimer = null;


function commit(event) {
  state = applyDspQualityEvent(state, event);
  renderDspQuality(root, deriveDspQualityView(state));
}


function commitCandidateRegion(event) {
  state = applyDspQualityEvent(state, event);
  const reconciliation = state.drivers?.reconciliation || {};
  if (!updateReconciliationCandidateRegion(root, reconciliation)) {
    renderDspQuality(root, deriveDspQualityView(state));
  }
}


async function loadLatest({ scorecardId = state.selectedScorecardId, notice = null } = {}) {
  if (!scorecardId) return null;
  const version = ++latestRequestVersion;
  latestRequestController?.abort();
  latestRequestController = new AbortController();
  commit({ type: "latest-started" });
  try {
    const latest = await getQualityScorecard(scorecardId, {
      signal: latestRequestController.signal,
    });
    if (version === latestRequestVersion && scorecardId === state.selectedScorecardId) {
      commit({ type: "latest-completed", latest, notice });
      if (state.section === "metrics") void loadMetrics();
      if (state.section === "drivers") void loadDrivers();
    }
    return latest;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    if (error?.status === 404 && version === latestRequestVersion && scorecardId === state.selectedScorecardId) {
      await loadHistory({
        excludedScorecardId: scorecardId,
        notice: "La scorecard selezionata non è più disponibile. È stata aperta la più recente.",
      });
    } else if (version === latestRequestVersion && scorecardId === state.selectedScorecardId) {
      commit({
        type: "latest-failed",
        message: "Impossibile caricare la scorecard selezionata. Riprova.",
      });
    }
    return null;
  }
}


function selectedFromHistory(items, preferredScorecardId = null) {
  const candidates = [preferredScorecardId, state.selectedScorecardId];
  return candidates.find(candidate => items.some(item => item.scorecard_id === candidate))
    || items[0]?.scorecard_id
    || null;
}


async function loadHistory({
  preferredScorecardId = null,
  excludedScorecardId = null,
  notice = null,
} = {}) {
  const version = ++historyRequestVersion;
  historyRequestController?.abort();
  historyRequestController = new AbortController();
  commit({ type: "scorecard-history-started" });
  try {
    const history = await getQualityScorecardHistory({
      signal: historyRequestController.signal,
    });
    if (version !== historyRequestVersion) return null;
    const items = (history.items || []).filter(
      item => item.scorecard_id !== excludedScorecardId,
    );
    const selectedScorecardId = selectedFromHistory(items, preferredScorecardId);
    commit({
      type: "scorecard-history-completed",
      items,
      selectedScorecardId,
      notice,
    });
    if (selectedScorecardId) {
      await loadLatest({ scorecardId: selectedScorecardId, notice });
    }
    return history;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    if (version === historyRequestVersion) {
      commit({
        type: "scorecard-history-failed",
        message: "Impossibile caricare lo storico Quality.",
      });
    }
    return null;
  }
}


async function loadMetrics({ force = false } = {}) {
  const scorecardId = state.selectedScorecardId;
  if (!scorecardId) return;
  if (!force && ["loading", "available"].includes(state.metrics?.phase)) return;
  const version = ++metricsRequestVersion;
  metricsRequestController?.abort();
  metricsRequestController = new AbortController();
  commit({ type: "metrics-started" });
  try {
    const data = await getQualityMetrics(scorecardId, { signal: metricsRequestController.signal });
    if (version === metricsRequestVersion && scorecardId === state.selectedScorecardId) commit({ type: "metrics-completed", data });
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (version === metricsRequestVersion) {
      commit({ type: "metrics-failed", message: "Impossibile caricare le metriche. Riprova." });
    }
  }
}


async function loadDrivers({ force = false } = {}) {
  const scorecardId = state.selectedScorecardId;
  if (!scorecardId) return;
  if (!force && ["loading", "available"].includes(state.drivers?.phase)) return;
  const version = ++driversRequestVersion;
  driversRequestController?.abort();
  driversRequestController = new AbortController();
  commit({ type: "drivers-started" });
  try {
    const data = await getQualityDrivers(scorecardId, { signal: driversRequestController.signal });
    if (version === driversRequestVersion && scorecardId === state.selectedScorecardId) commit({ type: "drivers-completed", data });
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
    const result = await getTransporterMappingHistory(externalId, {
      scorecardId: state.selectedScorecardId,
    });
    if (state.drivers?.reconciliation?.activeExternalId === externalId) {
      commit({ type: "history-completed", items: result.items || [] });
    }
  } catch {
    commit({ type: "history-completed", items: [] });
  }
}


async function loadReconciliation({ keepFilter = false, advanceAfter = null, silent = false } = {}) {
  reconciliationRequestController?.abort();
  reconciliationRequestController = new AbortController();
  if (!silent) commit({ type: "reconciliation-started" });
  try {
    const data = await getTransporterReconciliation({
      scorecardId: state.selectedScorecardId,
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
    if (!silent) {
      commit({
        type: "reconciliation-failed",
        message: "Impossibile caricare le associazioni Transporter.",
      });
    }
    return null;
  }
}


function identitySourceState() {
  return state.drivers?.reconciliation?.identitySource || {};
}


function suggestionReviewState() {
  return identitySourceState().review || {};
}


function focusSuggestionReview() {
  requestAnimationFrame(() => {
    const review = suggestionReviewState();
    const target = review.chooserOpen
      ? root.querySelector("[data-quality-review-search]")
      : root.querySelector("[data-quality-review-confirm]")
        || root.querySelector("[data-quality-review-close]");
    target?.focus();
  });
}


function openSuggestionReview() {
  const source = identitySourceState();
  if (!source.preview?.rows?.some(row => row.status === "SUGGESTED")) return;
  commit({
    type: "suggestion-review-opened",
    preview: source.preview,
    scorecardId: state.selectedScorecardId,
  });
  focusSuggestionReview();
}


function closeSuggestionReview() {
  commit({ type: "suggestion-review-closed" });
  requestAnimationFrame(() => root.querySelector("[data-quality-suggestion-review-open]")?.focus());
}


function skipSuggestionReview() {
  const review = suggestionReviewState();
  if (!review.open || review.saving || !currentSuggestion(review)) return;
  commit({ type: "suggestion-review-skipped" });
  focusSuggestionReview();
}


async function loadReviewCandidates(query) {
  reviewCandidateRequestController?.abort();
  if (query.trim().length < 2) return;
  reviewCandidateRequestController = new AbortController();
  try {
    const result = await searchQualityWorkforceCandidates(query, {
      signal: reviewCandidateRequestController.signal,
    });
    if (suggestionReviewState().candidateSearch === query) {
      commit({ type: "suggestion-review-candidates-completed", items: result.items || [] });
      focusSuggestionReview();
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({ type: "suggestion-review-candidates-failed", message: "Ricerca Workforce non disponibile." });
  }
}


function chooseAnotherReviewCandidate() {
  const row = currentSuggestion(suggestionReviewState());
  if (!row) return;
  const query = row.source_driver_value || "";
  commit({ type: "suggestion-review-choose-opened", search: query });
  if (query.trim().length >= 2) void loadReviewCandidates(query);
  focusSuggestionReview();
}


async function confirmSuggestionReview(workforceMemberId) {
  const review = suggestionReviewState();
  const suggestion = currentSuggestion(review);
  const canonicalId = Number(workforceMemberId);
  if (!suggestion || !Number.isInteger(canonicalId) || canonicalId <= 0 || review.saving) return false;
  if (review.scorecardId !== state.selectedScorecardId) {
    commit({
      type: "suggestion-review-conflict",
      message: "La scorecard selezionata è cambiata. Riapri la revisione.",
    });
    return false;
  }
  const reconciliation = state.drivers?.reconciliation || {};
  const mapping = (reconciliation.data?.rows || []).find(
    row => row.transporter_external_id === suggestion.transporter_external_id,
  );
  if (!mapping || mapping.mapping_status !== "UNMAPPED") {
    commit({
      type: "suggestion-review-conflict",
      message: "L’associazione è cambiata. Ricarica il suggerimento.",
    });
    return false;
  }
  commit({ type: "suggestion-review-saving" });
  try {
    await putTransporterMapping(suggestion.transporter_external_id, {
      workforce_member_id: canonicalId,
      expected_updated_at: mapping.updated_at || null,
    }, {
      scorecardId: state.selectedScorecardId,
    });
    commit({ type: "suggestion-review-confirmed" });
    await Promise.all([
      loadDrivers({ force: true }),
      loadReconciliation({ keepFilter: true, silent: true }),
    ]);
    focusSuggestionReview();
    return true;
  } catch (error) {
    commit({
      type: error?.status === 409 ? "suggestion-review-conflict" : "suggestion-review-failed",
      message: error?.status === 409
        ? "L’associazione è cambiata. Ricarica il suggerimento."
        : mappingErrorMessage(error),
    });
    focusSuggestionReview();
    return false;
  }
}


function handoffUnresolvedSuggestions() {
  const unresolved = (identitySourceState().preview?.rows || [])
    .filter(row => row.status === "UNRESOLVED")
    .map(row => row.transporter_external_id);
  commit({ type: "suggestion-review-unresolved-handoff", externalIds: unresolved });
  requestAnimationFrame(() => root.querySelector("[data-quality-reconciliation-filter='source-unresolved']")?.focus());
}


function identitySourceError(error) {
  return typeof error?.detail === "string"
    ? error.detail
    : "Impossibile analizzare la fonte. Controlla il file e riprova.";
}


async function analyzeIdentitySource({ file, usePlanning, selection } = {}) {
  const current = identitySourceState();
  const selectedFile = file === undefined ? current.file : file;
  const planning = usePlanning === undefined ? current.usePlanning : usePlanning;
  if (!planning) {
    const message = validateIdentitySourceFile(selectedFile);
    if (message) {
      commit({ type: "identity-source-preview-failed", message });
      return null;
    }
  }
  identitySourceRequestController?.abort();
  identitySourceRequestController = new AbortController();
  commit({
    type: "identity-source-preview-started",
    file: selectedFile,
    usePlanning: planning,
  });
  try {
    const preview = await previewTransporterIdentitySource({
      file: selectedFile,
      scorecardId: state.selectedScorecardId,
      usePlanning: planning,
      ...(selection || current.selection || {}),
    }, { signal: identitySourceRequestController.signal });
    commit({ type: "identity-source-preview-completed", preview });
    requestAnimationFrame(() => root.querySelector("[data-quality-identity-bucket]")?.focus());
    return preview;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    commit({ type: "identity-source-preview-failed", message: identitySourceError(error) });
    return null;
  }
}


async function applyExactIdentitySource() {
  const source = identitySourceState();
  if (!source.preview?.preview_token || source.phase === "applying") return;
  commit({ type: "identity-source-apply-started" });
  try {
    const result = await applyExactTransporterIdentitySource({
      file: source.file,
      scorecardId: state.selectedScorecardId,
      previewToken: source.preview.preview_token,
      usePlanning: source.usePlanning,
    });
    commit({ type: "identity-source-apply-completed", result });
    await Promise.all([
      loadDrivers({ force: true }),
      loadReconciliation({ keepFilter: true }),
    ]);
    requestAnimationFrame(() => root.querySelector("[data-quality-identity-reset]")?.focus());
  } catch (error) {
    commit({ type: "identity-source-apply-failed", message: identitySourceError(error) });
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


async function loadCandidates(query, version) {
  if (query.trim().length < 2 || version !== candidateRequestVersion) return;
  candidateRequestController = new AbortController();
  try {
    const result = await searchQualityWorkforceCandidates(query, {
      signal: candidateRequestController.signal,
    });
    if (version === candidateRequestVersion
      && state.drivers?.reconciliation?.candidateSearch === query) {
      commitCandidateRegion({ type: "candidates-completed", items: result.items || [] });
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (version === candidateRequestVersion
      && state.drivers?.reconciliation?.candidateSearch === query) {
      commitCandidateRegion({ type: "candidates-failed", message: "Ricerca Workforce non disponibile." });
    }
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
    }, {
      scorecardId: state.selectedScorecardId,
    });
    await Promise.all([
      loadDrivers({ force: true }),
      loadReconciliation({ keepFilter: true, advanceAfter: row.transporter_external_id }),
    ]);
    requestAnimationFrame(() => root.querySelector("[data-quality-candidate-search]")?.focus());
    return true;
  } catch (error) {
    commit({
      type: error?.status === 409 ? "mapping-conflict" : "mapping-failed",
      message: error?.status === 409
        ? "Associazione aggiornata da un altro utente. Chiudi e riapri per continuare."
        : mappingErrorMessage(error),
    });
    return false;
  }
}


async function removeMapping() {
  const reconciliation = state.drivers?.reconciliation || {};
  const row = activeReconciliationRow();
  if (!row?.updated_at || reconciliation.mutationPhase === "loading") return;
  commit({ type: "mapping-started" });
  try {
    await deleteTransporterMapping(row.transporter_external_id, row.updated_at, {
      scorecardId: state.selectedScorecardId,
    });
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
    await loadHistory({
      preferredScorecardId: result.scorecard_id,
      notice: "Scorecard importata",
    });
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
    if (event.target.closest("[data-quality-retry]")) void loadHistory();
    if (event.target.closest("[data-quality-metrics-retry]")) void loadMetrics({ force: true });
    if (event.target.closest("[data-quality-drivers-retry]")) void loadDrivers({ force: true });
    if (event.target.closest("[data-quality-reconciliation-open]")) void openReconciliation();
    if (event.target.closest("[data-quality-reconciliation-close]")) commit({ type: "reconciliation-closed" });
    if (event.target.closest("[data-quality-reconciliation-retry]")) void loadReconciliation();
    if (event.target.closest("[data-quality-identity-pick]")) root.querySelector("[data-quality-identity-file]")?.click();
    if (event.target.closest("[data-quality-identity-planning]")) void analyzeIdentitySource({ file: null, usePlanning: true });
    if (event.target.closest("[data-quality-identity-analyze]")) void analyzeIdentitySource({ selection: identitySourceState().selection });
    if (event.target.closest("[data-quality-identity-apply]")) void applyExactIdentitySource();
    if (event.target.closest("[data-quality-identity-reset]")) commit({ type: "identity-source-reset" });
    if (event.target.closest("[data-quality-suggestion-review-open]")) {
      event.preventDefault();
      openSuggestionReview();
      return;
    }
    if (event.target.closest("[data-quality-review-close]")) closeSuggestionReview();
    if (event.target.closest("[data-quality-review-confirm]")) {
      const suggestion = currentSuggestion(suggestionReviewState());
      void confirmSuggestionReview(suggestion?.proposed_workforce_member_id);
    }
    if (event.target.closest("[data-quality-review-skip]")) skipSuggestionReview();
    if (event.target.closest("[data-quality-review-choose]")) chooseAnotherReviewCandidate();
    if (event.target.closest("[data-quality-review-choose-close]")) {
      commit({ type: "suggestion-review-choose-closed" });
      focusSuggestionReview();
    }
    if (event.target.closest("[data-quality-review-confirm-selected]")) {
      void confirmSuggestionReview(suggestionReviewState().currentSelection?.workforce_member_id);
    }
    if (event.target.closest("[data-quality-review-unresolved]")) handoffUnresolvedSuggestions();
    const reviewCandidateId = Number(event.target.closest("[data-quality-review-candidate]")?.dataset.qualityReviewCandidate);
    if (Number.isInteger(reviewCandidateId) && reviewCandidateId > 0) {
      const candidate = (suggestionReviewState().candidates || []).find(
        item => item.workforce_member_id === reviewCandidateId,
      );
      if (candidate) commit({ type: "suggestion-review-candidate-selected", candidate });
    }
    const identityBucket = event.target.closest("[data-quality-identity-bucket]")?.dataset.qualityIdentityBucket;
    if (identityBucket) commit({ type: "identity-source-bucket-changed", bucket: identityBucket });
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
    if (event.target.matches("[data-quality-identity-file]")) {
      void analyzeIdentitySource({ file: selectedFile(event.target), usePlanning: false });
    }
    if (event.target.matches("[data-quality-identity-selection]")) {
      commit({
        type: "identity-source-selection-changed",
        field: event.target.dataset.qualityIdentitySelection,
        value: event.target.value,
      });
    }
    if (event.target.matches("[data-quality-scorecard-select]")) {
      const scorecardId = event.target.value || null;
      if (!scorecardId || scorecardId === state.selectedScorecardId) return;
      latestRequestController?.abort();
      metricsRequestController?.abort();
      driversRequestController?.abort();
      reconciliationRequestController?.abort();
      commit({ type: "scorecard-selection-changed", scorecardId });
      void loadLatest({ scorecardId }).finally(() => {
        requestAnimationFrame(() => root.querySelector("[data-quality-scorecard-select]")?.focus());
      });
    }
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
      candidateRequestController?.abort();
      candidateRequestController = null;
      candidateRequestVersion += 1;
      const version = candidateRequestVersion;
      commitCandidateRegion({ type: "candidate-search-changed", search: query });
      clearTimeout(candidateTimer);
      candidateTimer = setTimeout(() => void loadCandidates(query, version), 225);
    }
    if (event.target.matches("[data-quality-review-search]")) {
      const query = event.target.value;
      commit({ type: "suggestion-review-search-changed", search: query });
      clearTimeout(reviewCandidateTimer);
      reviewCandidateTimer = setTimeout(() => void loadReviewCandidates(query), 250);
      requestAnimationFrame(() => {
        const input = root.querySelector("[data-quality-review-search]");
        input?.focus();
        input?.setSelectionRange?.(query.length, query.length);
      });
    }
  });
  root.addEventListener("keydown", (event) => {
    const review = suggestionReviewState();
    if (review.open) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (review.chooserOpen) {
          commit({ type: "suggestion-review-choose-closed" });
          focusSuggestionReview();
        } else closeSuggestionReview();
        return;
      }
      if (review.chooserOpen && event.target.matches("[data-quality-review-search]")) {
        if (event.key === "ArrowDown" && review.candidates.length) {
          event.preventDefault();
          root.querySelector("[data-quality-review-candidate]")?.focus();
        }
        if (event.key === "Enter" && review.candidates.length) {
          event.preventDefault();
          commit({ type: "suggestion-review-candidate-selected", candidate: review.candidates[0] });
        }
        return;
      }
      if (isReviewShortcutTarget(event.target)) return;
      if (event.key === "Enter") {
        event.preventDefault();
        const suggestion = currentSuggestion(review);
        void confirmSuggestionReview(suggestion?.proposed_workforce_member_id);
        return;
      }
      if (event.key.toLocaleLowerCase("it") === "s") {
        event.preventDefault();
        skipSuggestionReview();
        return;
      }
      if (event.key.toLocaleLowerCase("it") === "e") {
        event.preventDefault();
        chooseAnotherReviewCandidate();
        return;
      }
    }
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
    const identityZone = event.target.closest("[data-quality-identity-dropzone]");
    if (identityZone) {
      event.preventDefault();
      identityZone.classList.add("is-dragging");
      return;
    }
    const zone = event.target.closest("[data-quality-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  root.addEventListener("dragleave", (event) => {
    event.target.closest("[data-quality-identity-dropzone]")?.classList.remove("is-dragging");
    event.target.closest("[data-quality-dropzone]")?.classList.remove("is-dragging");
  });
  root.addEventListener("drop", (event) => {
    const identityZone = event.target.closest("[data-quality-identity-dropzone]");
    if (identityZone) {
      event.preventDefault();
      identityZone.classList.remove("is-dragging");
      void analyzeIdentitySource({ file: event.dataTransfer?.files?.[0] || null, usePlanning: false });
      return;
    }
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
  void loadHistory();
}

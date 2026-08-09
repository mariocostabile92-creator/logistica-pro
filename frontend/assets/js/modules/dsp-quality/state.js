import {
  applyReconciliationEvent,
  createReconciliationState,
} from "./reconciliation-state.js?v=7";


export function createDspQualityState({ canImport = false } = {}) {
  return {
    phase: "loading",
    canImport,
    latest: null,
    history: { phase: "idle", items: [], error: null },
    selectedScorecardId: null,
    file: null,
    preview: null,
    result: null,
    error: null,
    section: "overview",
    overviewVisible: false,
    notice: null,
    metrics: {
      phase: "idle",
      data: null,
      error: null,
      filter: "all",
      search: "",
    },
    drivers: {
      phase: "idle",
      data: null,
      error: null,
      filter: "all",
      search: "",
      sort: { key: "row_index", direction: "asc" },
      selectedRowId: null,
      canManageMappings: canImport,
      reconciliation: createReconciliationState(),
    },
  };
}


export function applyDspQualityEvent(state, event) {
  if ((event.type.startsWith("reconciliation-") || event.type.startsWith("identity-source-")
    || event.type.startsWith("suggestion-review-"))
    || event.type.startsWith("candidate-")
    || event.type.startsWith("candidates-")
    || event.type.startsWith("mapping-")
    || event.type === "history-completed") {
    return {
      ...state,
      drivers: {
        ...state.drivers,
        reconciliation: applyReconciliationEvent(
          state.drivers.reconciliation || createReconciliationState(),
          event,
        ),
      },
    };
  }
  switch (event.type) {
    case "scorecard-history-started":
      return {
        ...state,
        phase: state.latest ? state.phase : "loading",
        history: { ...state.history, phase: "loading", error: null },
      };
    case "scorecard-history-completed":
      return {
        ...state,
        phase: event.items?.length ? state.phase : "empty",
        history: { phase: "available", items: event.items || [], error: null },
        selectedScorecardId: event.selectedScorecardId || null,
        notice: event.notice || state.notice,
      };
    case "scorecard-history-failed":
      return {
        ...state,
        phase: state.latest ? state.phase : "error",
        history: { ...state.history, phase: "error", error: event.message },
        error: state.latest ? state.error : event.message,
      };
    case "scorecard-selection-changed":
      return {
        ...state,
        phase: state.history?.items?.length ? "available" : "loading",
        latest: null,
        selectedScorecardId: event.scorecardId,
        notice: event.notice || null,
        error: null,
        metrics: { ...state.metrics, phase: "idle", data: null, error: null, filter: "all", search: "" },
        drivers: {
          ...state.drivers,
          phase: "idle",
          data: null,
          error: null,
          filter: "all",
          search: "",
          sort: { key: "row_index", direction: "asc" },
          selectedRowId: null,
          reconciliation: createReconciliationState(),
        },
      };
    case "latest-started":
      return {
        ...state,
        phase: state.history?.items?.length ? "available" : "loading",
        error: null,
        metrics: { ...state.metrics, phase: "idle", data: null, error: null },
        drivers: { ...state.drivers, phase: "idle", data: null, error: null, selectedRowId: null, reconciliation: createReconciliationState() },
      };
    case "latest-completed":
      return {
        ...state,
        phase: event.latest?.available ? "available" : "empty",
        latest: event.latest?.available ? event.latest : null,
        file: null,
        preview: null,
        error: null,
        notice: event.notice || null,
        section: state.section || "overview",
        metrics: { ...state.metrics, phase: "idle", data: null, error: null, filter: "all", search: "" },
        drivers: {
          ...state.drivers,
          phase: "idle",
          data: null,
          error: null,
          filter: "all",
          search: "",
          sort: { key: "row_index", direction: "asc" },
          selectedRowId: null,
          reconciliation: createReconciliationState(),
        },
      };
    case "latest-failed":
      return { ...state, phase: "error", error: event.message, notice: null };
    case "import-opened":
      return { ...state, phase: "empty", file: null, preview: null, error: null, notice: null };
    case "latest-restored":
      return { ...state, phase: state.latest?.available ? "available" : "empty", error: null };
    case "file-invalid":
      return { ...state, phase: "error", file: event.file || null, preview: null, error: event.message };
    case "preview-started":
      return { ...state, phase: "preview-loading", file: event.file, preview: null, result: null, error: null, overviewVisible: false };
    case "preview-completed":
      return { ...state, phase: "preview-ready", preview: event.preview, error: null };
    case "preview-failed":
      return { ...state, phase: "error", preview: null, error: event.message };
    case "import-started":
      return { ...state, phase: "import-loading", error: null };
    case "import-completed":
      return { ...state, phase: "success", result: event.result, error: null };
    case "import-failed":
      return { ...state, phase: "preview-ready", error: event.message };
    case "overview-opened":
      return { ...state, overviewVisible: true, section: "overview" };
    case "section-changed":
      return { ...state, section: event.section };
    case "metrics-started":
      return { ...state, metrics: { ...state.metrics, phase: "loading", error: null } };
    case "metrics-completed":
      return { ...state, metrics: { ...state.metrics, phase: "available", data: event.data, error: null } };
    case "metrics-failed":
      return { ...state, metrics: { ...state.metrics, phase: "error", error: event.message } };
    case "metrics-filter-changed":
      return { ...state, metrics: { ...state.metrics, filter: event.filter } };
    case "metrics-search-changed":
      return { ...state, metrics: { ...state.metrics, search: event.search } };
    case "drivers-started":
      return { ...state, drivers: { ...state.drivers, phase: "loading", error: null } };
    case "drivers-completed":
      return { ...state, drivers: { ...state.drivers, phase: "available", data: event.data, error: null } };
    case "drivers-failed":
      return { ...state, drivers: { ...state.drivers, phase: "error", error: event.message } };
    case "drivers-filter-changed":
      return { ...state, drivers: { ...state.drivers, filter: event.filter, selectedRowId: null } };
    case "drivers-search-changed":
      return { ...state, drivers: { ...state.drivers, search: event.search, selectedRowId: null } };
    case "drivers-sort-changed":
      return { ...state, drivers: { ...state.drivers, sort: event.sort } };
    case "driver-opened":
      return { ...state, drivers: { ...state.drivers, selectedRowId: event.rowId } };
    case "driver-closed":
      return { ...state, drivers: { ...state.drivers, selectedRowId: null } };
    case "reset":
      return {
        ...createDspQualityState({ canImport: state.canImport }),
        phase: state.latest?.available ? "available" : "empty",
        latest: state.latest,
        history: state.history,
        selectedScorecardId: state.selectedScorecardId,
      };
    default:
      return state;
  }
}


export function deriveDspQualityView(state) {
  const errors = state.preview?.validation?.errors || [];
  return {
    ...state,
    canConfirm: Boolean(
      state.canImport
      && state.file
      && state.preview?.valid
      && state.preview?.preview_token
      && errors.length === 0
      && state.phase === "preview-ready"
    ),
  };
}

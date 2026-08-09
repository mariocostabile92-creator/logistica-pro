export function createDspQualityState({ canImport = false } = {}) {
  return {
    phase: "loading",
    canImport,
    latest: null,
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
  };
}


export function applyDspQualityEvent(state, event) {
  switch (event.type) {
    case "latest-started":
      return {
        ...state,
        phase: "loading",
        error: null,
        metrics: { ...state.metrics, phase: "idle", data: null, error: null },
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
        section: "overview",
        metrics: { ...state.metrics, phase: "idle", data: null, error: null, filter: "all", search: "" },
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
    case "reset":
      return {
        ...createDspQualityState({ canImport: state.canImport }),
        phase: state.latest?.available ? "available" : "empty",
        latest: state.latest,
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

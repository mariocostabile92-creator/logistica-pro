export function createReconciliationState() {
  return {
    open: false,
    phase: "idle",
    data: null,
    filter: "unmapped",
    search: "",
    activeExternalId: null,
    error: null,
    mutationPhase: "idle",
    candidateSearch: "",
    candidatePhase: "idle",
    candidates: [],
    selectedCandidate: null,
    history: [],
  };
}


export function applyReconciliationEvent(state, event) {
  switch (event.type) {
    case "reconciliation-opened":
      return { ...state, open: true, error: null };
    case "reconciliation-closed":
      return createReconciliationState();
    case "reconciliation-started":
      return { ...state, phase: "loading", error: null };
    case "reconciliation-completed":
      return {
        ...state,
        phase: "available",
        data: event.data,
        filter: event.keepFilter
          ? state.filter
          : (Number(event.data?.summary?.unmapped || 0) > 0 ? "unmapped" : "all"),
        activeExternalId: event.setActive
          ? event.activeExternalId
          : state.activeExternalId,
        error: null,
        mutationPhase: "idle",
      };
    case "reconciliation-failed":
      return { ...state, phase: "error", error: event.message };
    case "reconciliation-filter-changed":
      return { ...state, filter: event.filter };
    case "reconciliation-search-changed":
      return { ...state, search: event.search };
    case "reconciliation-row-opened":
      return {
        ...state,
        activeExternalId: event.externalId,
        candidateSearch: "",
        candidatePhase: "idle",
        candidates: [],
        selectedCandidate: null,
        history: [],
        error: null,
      };
    case "reconciliation-row-closed":
      return {
        ...state,
        activeExternalId: null,
        candidateSearch: "",
        candidatePhase: "idle",
        candidates: [],
        selectedCandidate: null,
        history: [],
      };
    case "candidate-search-changed":
      return {
        ...state,
        candidateSearch: event.search,
        candidatePhase: event.search.trim().length >= 2 ? "loading" : "idle",
        candidates: event.search.trim().length >= 2 ? state.candidates : [],
        selectedCandidate: null,
      };
    case "candidates-completed":
      return { ...state, candidatePhase: "available", candidates: event.items, error: null };
    case "candidates-failed":
      return { ...state, candidatePhase: "error", candidates: [], error: event.message };
    case "candidate-selected":
      return { ...state, selectedCandidate: event.candidate };
    case "mapping-started":
      return { ...state, mutationPhase: "loading", error: null };
    case "mapping-conflict":
      return { ...state, mutationPhase: "conflict", error: event.message };
    case "mapping-failed":
      return { ...state, mutationPhase: "error", error: event.message };
    case "history-completed":
      return { ...state, history: event.items || [] };
    default:
      return state;
  }
}

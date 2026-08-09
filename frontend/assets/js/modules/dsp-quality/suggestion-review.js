export function suggestionQueue(preview = {}) {
  return (preview.rows || []).filter(row => row.status === "SUGGESTED");
}


export function createSuggestionReviewState() {
  return {
    open: false,
    scorecardId: null,
    queue: [],
    currentIndex: 0,
    confirmed: [],
    skipped: [],
    chooserOpen: false,
    currentSelection: null,
    candidateSearch: "",
    candidatePhase: "idle",
    candidates: [],
    saving: false,
    error: null,
    feedback: null,
  };
}


export function currentSuggestion(state = {}) {
  return state.queue?.[state.currentIndex] || null;
}


export function suggestionReviewProgress(state = {}) {
  const total = state.queue?.length || 0;
  const confirmed = state.confirmed?.length || 0;
  const skipped = state.skipped?.length || 0;
  return {
    total,
    confirmed,
    skipped,
    remaining: Math.max(0, total - confirmed - skipped),
    complete: total > 0 && confirmed + skipped >= total,
  };
}


function sameQueue(state, event) {
  const incoming = suggestionQueue(event.preview);
  return state.scorecardId === event.scorecardId
    && state.queue.length === incoming.length
    && state.queue.every((row, index) => (
      row.transporter_external_id === incoming[index]?.transporter_external_id
    ));
}


function advance(state, field, feedback) {
  const row = currentSuggestion(state);
  if (!row) return state;
  return {
    ...state,
    currentIndex: state.currentIndex + 1,
    [field]: [...state[field], row.transporter_external_id],
    chooserOpen: false,
    currentSelection: null,
    candidateSearch: "",
    candidatePhase: "idle",
    candidates: [],
    saving: false,
    error: null,
    feedback,
  };
}


export function applySuggestionReviewEvent(state, event) {
  switch (event.type) {
    case "suggestion-review-opened": {
      if (sameQueue(state, event)) return { ...state, open: true, error: null };
      return {
        ...createSuggestionReviewState(),
        open: true,
        scorecardId: event.scorecardId,
        queue: suggestionQueue(event.preview),
      };
    }
    case "suggestion-review-closed":
      return {
        ...state,
        open: false,
        chooserOpen: false,
        currentSelection: null,
        candidateSearch: "",
        candidatePhase: "idle",
        candidates: [],
        saving: false,
        error: null,
      };
    case "suggestion-review-saving":
      return { ...state, saving: true, error: null, feedback: null };
    case "suggestion-review-confirmed":
      return advance(state, "confirmed", "Associazione salvata.");
    case "suggestion-review-skipped":
      return advance(state, "skipped", "Suggerimento saltato.");
    case "suggestion-review-choose-opened":
      return {
        ...state,
        chooserOpen: true,
        currentSelection: null,
        candidateSearch: event.search || "",
        candidatePhase: event.search?.trim().length >= 2 ? "loading" : "idle",
        candidates: [],
        error: null,
      };
    case "suggestion-review-choose-closed":
      return {
        ...state,
        chooserOpen: false,
        currentSelection: null,
        candidateSearch: "",
        candidatePhase: "idle",
        candidates: [],
        error: null,
      };
    case "suggestion-review-search-changed":
      return {
        ...state,
        candidateSearch: event.search,
        candidatePhase: event.search.trim().length >= 2 ? "loading" : "idle",
        candidates: event.search.trim().length >= 2 ? state.candidates : [],
        currentSelection: null,
      };
    case "suggestion-review-candidates-completed":
      return { ...state, candidatePhase: "available", candidates: event.items || [], error: null };
    case "suggestion-review-candidates-failed":
      return { ...state, candidatePhase: "error", candidates: [], error: event.message };
    case "suggestion-review-candidate-selected":
      return { ...state, currentSelection: event.candidate, error: null };
    case "suggestion-review-conflict":
      return { ...state, saving: false, error: event.message, feedback: null };
    case "suggestion-review-failed":
      return { ...state, saving: false, error: event.message, feedback: null };
    case "suggestion-review-reset":
      return createSuggestionReviewState();
    default:
      return state;
  }
}


export function isReviewShortcutTarget(target) {
  return Boolean(target?.matches?.("input, textarea, select, [contenteditable='true']"));
}

import {
  applySuggestionReviewEvent,
  createSuggestionReviewState,
} from "./suggestion-review.js?v=1";


export function createIdentitySourceState() {
  return {
    phase: "idle",
    file: null,
    usePlanning: false,
    preview: null,
    result: null,
    error: null,
    bucket: "suggested",
    selection: { sheet: "", transporterColumn: "", driverColumn: "" },
    review: createSuggestionReviewState(),
  };
}


export function applyIdentitySourceEvent(state, event) {
  if (event.type.startsWith("suggestion-review-")) {
    return {
      ...state,
      review: applySuggestionReviewEvent(
        state.review || createSuggestionReviewState(),
        event,
      ),
    };
  }
  switch (event.type) {
    case "identity-source-preview-started":
      return {
        ...state,
        phase: "loading",
        file: event.file || null,
        usePlanning: Boolean(event.usePlanning),
        result: null,
        error: null,
      };
    case "identity-source-preview-completed":
      return {
        ...state,
        phase: event.preview.valid ? "available" : "schema",
        preview: event.preview,
        bucket: event.preview.default_bucket || "suggested",
        selection: {
          sheet: event.preview.source?.sheet || state.selection.sheet,
          transporterColumn: event.preview.source?.transporter_column || state.selection.transporterColumn,
          driverColumn: event.preview.source?.driver_column || state.selection.driverColumn,
        },
        review: createSuggestionReviewState(),
        error: null,
      };
    case "identity-source-preview-failed":
      return { ...state, phase: "error", error: event.message };
    case "identity-source-selection-changed":
      return {
        ...state,
        selection: { ...state.selection, [event.field]: event.value },
      };
    case "identity-source-bucket-changed":
      return { ...state, bucket: event.bucket };
    case "identity-source-apply-started":
      return { ...state, phase: "applying", error: null };
    case "identity-source-apply-completed":
      return { ...state, phase: "applied", result: event.result, error: null };
    case "identity-source-apply-failed":
      return { ...state, phase: "available", error: event.message };
    case "identity-source-reset":
      return createIdentitySourceState();
    default:
      return state;
  }
}


export function identityRowsForBucket(rows = [], bucket = "suggested") {
  const statuses = {
    exact: ["EXACT", "ALREADY_VERIFIED"],
    suggested: ["SUGGESTED"],
    unresolved: ["UNRESOLVED"],
    conflict: ["CONFLICT", "CONFLICT_WITH_VERIFIED_MAPPING"],
  }[bucket] || [];
  return rows.filter(row => statuses.includes(row.status));
}


export function validateIdentitySourceFile(file) {
  if (!file) return "Seleziona un file .xlsx o .csv.";
  if (!/\.(xlsx|csv)$/i.test(file.name || "")) return "Sono supportati soltanto file .xlsx e .csv.";
  return null;
}

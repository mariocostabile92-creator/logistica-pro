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
    selectedSuggestionIds: [],
    savingSuggestionIds: [],
    confirmedSuggestionIds: [],
    failedSuggestionIds: [],
    bulkSaving: false,
    bulkDialogOpen: false,
    bulkResult: null,
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
    case "identity-source-suggestion-selection-changed":
      return {
        ...state,
        selectedSuggestionIds: event.selected
          ? [...new Set([...state.selectedSuggestionIds, event.externalId])]
          : state.selectedSuggestionIds.filter(item => item !== event.externalId),
        bulkResult: null,
      };
    case "identity-source-suggestion-visible-selection-changed":
      return {
        ...state,
        selectedSuggestionIds: event.selected ? [...new Set(event.externalIds || [])] : [],
        bulkResult: null,
      };
    case "identity-source-suggestion-saving":
      return {
        ...state,
        savingSuggestionIds: [...new Set([...state.savingSuggestionIds, event.externalId])],
        failedSuggestionIds: state.failedSuggestionIds.filter(item => item !== event.externalId),
        bulkResult: null,
      };
    case "identity-source-suggestion-confirmed":
      return {
        ...state,
        selectedSuggestionIds: state.selectedSuggestionIds.filter(item => item !== event.externalId),
        savingSuggestionIds: state.savingSuggestionIds.filter(item => item !== event.externalId),
        confirmedSuggestionIds: [...new Set([...state.confirmedSuggestionIds, event.externalId])],
        failedSuggestionIds: state.failedSuggestionIds.filter(item => item !== event.externalId),
      };
    case "identity-source-suggestion-failed":
      return {
        ...state,
        savingSuggestionIds: state.savingSuggestionIds.filter(item => item !== event.externalId),
        failedSuggestionIds: [...new Set([...state.failedSuggestionIds, event.externalId])],
      };
    case "identity-source-bulk-dialog-opened":
      return { ...state, bulkDialogOpen: true, bulkResult: null };
    case "identity-source-bulk-dialog-closed":
      return { ...state, bulkDialogOpen: false };
    case "identity-source-bulk-started":
      return {
        ...state,
        bulkSaving: true,
        savingSuggestionIds: [...new Set(event.externalIds || [])],
        failedSuggestionIds: [],
        bulkResult: null,
      };
    case "identity-source-bulk-completed": {
      const confirmed = event.confirmedIds || [];
      const failed = event.failedIds || [];
      return {
        ...state,
        bulkSaving: false,
        bulkDialogOpen: false,
        savingSuggestionIds: [],
        confirmedSuggestionIds: [...new Set([...state.confirmedSuggestionIds, ...confirmed])],
        failedSuggestionIds: failed,
        selectedSuggestionIds: failed,
        bulkResult: { confirmed: confirmed.length, failed: failed.length },
      };
    }
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


export async function mapWithConcurrency(items = [], limit = 4, worker) {
  const queue = [...items];
  const results = [];
  const concurrency = Math.max(1, Math.min(Number(limit) || 1, queue.length || 1));
  await Promise.all(Array.from({ length: concurrency }, async () => {
    while (queue.length) {
      const item = queue.shift();
      results.push(await worker(item));
    }
  }));
  return results;
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

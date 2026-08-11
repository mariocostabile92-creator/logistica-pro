export const DRIVER_SHIFT_PAGE_SIZE = 25;
export const LEGACY_PREVIEW_STATUS = Object.freeze({
  IDLE: "IDLE",
  LOADING: "LOADING",
  AVAILABLE: "AVAILABLE",
  EMPTY: "EMPTY",
  ERROR: "ERROR",
});


export function createDriverShiftPlanningState() {
  let requestVersion = 0;
  const state = {
    plannings: [],
    planning: null,
    preview: null,
    classification: "",
    search: "",
    offset: 0,
    limit: DRIVER_SHIFT_PAGE_SIZE,
    loading: false,
    pendingImportMode: null,
    pendingImport: null,
    members: [],
    legacyPreviewStatus: LEGACY_PREVIEW_STATUS.IDLE,
    legacyPreview: null,
    legacyPublishing: false,
  };

  function beginRequest() {
    requestVersion += 1;
    state.loading = true;
    return requestVersion;
  }

  function isCurrent(version) {
    return version === requestVersion;
  }

  function completeRequest(version) {
    if (!isCurrent(version)) return false;
    state.loading = false;
    return true;
  }

  function resetPaging() {
    state.offset = 0;
  }

  function reset() {
    requestVersion += 1;
    Object.assign(state, {
      plannings: [], planning: null, preview: null,
      classification: "", search: "", offset: 0,
      loading: false, pendingImportMode: null, pendingImport: null,
      members: [],
      legacyPreviewStatus: LEGACY_PREVIEW_STATUS.IDLE,
      legacyPreview: null,
      legacyPublishing: false,
    });
  }

  return { state, beginRequest, isCurrent, completeRequest, resetPaging, reset };
}

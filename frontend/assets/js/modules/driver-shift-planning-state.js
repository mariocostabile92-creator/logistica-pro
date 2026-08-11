export const DRIVER_SHIFT_PAGE_SIZE = 25;


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
    });
  }

  return { state, beginRequest, isCurrent, completeRequest, resetPaging, reset };
}

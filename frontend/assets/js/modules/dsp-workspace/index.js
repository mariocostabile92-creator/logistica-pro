import { getDspDailySnapshot } from "./api.js";
import { dspWorkspaceRefs, renderDspWorkspace } from "./presenter.js";
import {
  applyDspWorkspaceEvent,
  createDspWorkspaceState,
  deriveDspWorkspaceView,
  localToday,
} from "./state.js";


let refs;
let state = createDspWorkspaceState();
let initialized = false;
let loadedDate = null;
let loadPromise = null;
let requestVersion = 0;
let requestController = null;


function commit(event) {
  state = applyDspWorkspaceEvent(state, event);
  renderDspWorkspace(refs, deriveDspWorkspaceView(state));
}


async function loadSnapshot({ force = false } = {}) {
  if (!force && loadPromise && loadedDate === state.operationDate) return loadPromise;
  const requestedDate = state.operationDate;
  const version = ++requestVersion;
  requestController?.abort();
  requestController = new AbortController();
  commit({ type: "load-started" });
  loadedDate = requestedDate;
  loadPromise = getDspDailySnapshot(requestedDate, {
    signal: requestController.signal,
  }).then((snapshot) => {
    if (version === requestVersion) commit({ type: "load-completed", snapshot });
    return snapshot;
  }).catch((error) => {
    if (error?.name === "AbortError") return null;
    if (version === requestVersion) commit({ type: "load-failed", error });
    return null;
  }).finally(() => {
    if (version === requestVersion) loadPromise = null;
  });
  return loadPromise;
}


function selectDate(operationDate, { force = false } = {}) {
  if (!operationDate) return;
  commit({ type: "date-changed", operationDate });
  void loadSnapshot({ force });
}


function bindEvents() {
  refs.date.addEventListener("change", () => selectDate(refs.date.value, { force: true }));
  refs.today.addEventListener("click", () => selectDate(localToday(), { force: true }));
  refs.search.addEventListener("input", () => commit({
    type: "search-changed", search: refs.search.value,
  }));
  refs.sort.addEventListener("change", () => commit({
    type: "sort-changed", sort: refs.sort.value,
  }));
  document.addEventListener("click", (event) => {
    const filter = event.target.closest("[data-dsp-filter]")?.dataset.dspFilter;
    if (filter) commit({ type: "filter-changed", filter });
    if (event.target.closest('[data-view-action="dsp-retry"]')) {
      void loadSnapshot({ force: true });
    }
  });
}


export function initDspWorkspace() {
  if (initialized) return;
  initialized = true;
  refs = dspWorkspaceRefs();
  state = createDspWorkspaceState({ operationDate: localToday() });
  bindEvents();
  renderDspWorkspace(refs, deriveDspWorkspaceView(state));
}


export function prepareDspFirstPaint() {
  initDspWorkspace();
  if (state.snapshot && loadedDate === state.operationDate) return Promise.resolve(state.snapshot);
  return loadSnapshot();
}


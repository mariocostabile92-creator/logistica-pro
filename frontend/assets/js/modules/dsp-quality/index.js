import { can } from "../../auth/state.js";
import {
  getLatestQualityScorecard,
  importQualityScorecard,
  previewQualityScorecard,
} from "./api.js?v=2";
import { qualityErrorMessage, validateQualityFile } from "./import.js";
import { renderDspQuality } from "./presenter.js?v=2";
import {
  applyDspQualityEvent,
  createDspQualityState,
  deriveDspQualityView,
} from "./state.js?v=2";


let initialized = false;
let root = null;
let state = createDspQualityState();
let requestVersion = 0;
let requestController = null;
let latestRequestVersion = 0;
let latestRequestController = null;


function commit(event) {
  state = applyDspQualityEvent(state, event);
  renderDspQuality(root, deriveDspQualityView(state));
}


async function loadLatest({ notice = null } = {}) {
  const version = ++latestRequestVersion;
  latestRequestController?.abort();
  latestRequestController = new AbortController();
  commit({ type: "latest-started" });
  try {
    const latest = await getLatestQualityScorecard({
      signal: latestRequestController.signal,
    });
    if (version === latestRequestVersion) {
      commit({ type: "latest-completed", latest, notice });
    }
    return latest;
  } catch (error) {
    if (error?.name === "AbortError") return null;
    if (version === latestRequestVersion) {
      commit({
        type: "latest-failed",
        message: "Impossibile caricare l'ultima scorecard. Riprova.",
      });
    }
    return null;
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
    await loadLatest({ notice: "Scorecard importata" });
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
    if (event.target.closest("[data-quality-retry]")) void loadLatest();
    if (event.target.closest("[data-quality-overview]")) commit({ type: "overview-opened" });
    const section = event.target.closest("[data-quality-section]")?.dataset.qualitySection;
    if (section) commit({ type: "section-changed", section });
  });
  root.addEventListener("change", (event) => {
    if (event.target.matches("[data-quality-file]")) void analyze(selectedFile(event.target));
  });
  root.addEventListener("dragover", (event) => {
    const zone = event.target.closest("[data-quality-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  root.addEventListener("dragleave", (event) => {
    event.target.closest("[data-quality-dropzone]")?.classList.remove("is-dragging");
  });
  root.addEventListener("drop", (event) => {
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
  void loadLatest();
}

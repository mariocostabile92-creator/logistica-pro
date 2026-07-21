import {
  confirmWorkforceImport,
  previewWorkforceImport,
} from "../api.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import {
  clearWorkforceImportPreview,
  renderWorkforceImportPreview,
} from "./workforce-view.js";


let routedFile = null;
let importPreview = null;
let analyzing = false;
let importing = false;
let afterImport = async () => {};


function selectedFile() {
  return byId("workforceFile").files[0] || routedFile;
}


function presentError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
  return presentation.message;
}


function resetPanel() {
  importPreview = null;
  routedFile = null;
  byId("workforceFile").value = "";
  byId("workforceConfirmBtn").disabled = true;
  clearWorkforceImportPreview();
  delete byId("workforceImportPanel").dataset.importState;
}


function close({ reset = false } = {}) {
  if (analyzing || importing) return;
  byId("workforceImportPanel").hidden = true;
  if (reset) resetPanel();
}


function setBusy(stage = null) {
  const busy = Boolean(stage);
  byId("workforceImportPanel").dataset.importState = stage || "idle";
  byId("workforceImportForm").setAttribute("aria-busy", String(busy));
  byId("workforceFile").disabled = busy;
  byId("workforceImportClose").disabled = busy;
  setLoading(byId("workforceAnalyzeBtn"), stage === "analysis", "Analisi in corso...");
  setLoading(byId("workforceConfirmBtn"), stage === "import", "Importazione...");
  byId("workforceAnalyzeBtn").disabled = busy;
  byId("workforceConfirmBtn").disabled = busy || !importPreview;
}


async function analyze() {
  if (analyzing || importing) return;
  const file = selectedFile();
  if (!file) {
    setMessage("Seleziona un file turni.", "warning");
    return;
  }
  analyzing = true;
  importPreview = null;
  clearWorkforceImportPreview();
  setBusy("analysis");
  byId("workforceImportState").innerHTML = `
    <div class="workforce-import-loading" aria-live="polite">
      <strong>Analisi del planning turni in corso...</strong>
      <span class="skeleton-line" aria-hidden="true"></span>
    </div>
  `;
  try {
    importPreview = await previewWorkforceImport(file);
    renderWorkforceImportPreview(importPreview);
    setMessage("");
  } catch (error) {
    importPreview = null;
    const message = presentError("workforce.import-preview", error);
    byId("workforceImportState").innerHTML = `
      <p class="import-notice blocking"><strong>Analisi non riuscita.</strong> ${message}</p>
    `;
  } finally {
    analyzing = false;
    setBusy();
  }
}


async function confirm(event) {
  event.preventDefault();
  if (analyzing || importing) return;
  const file = selectedFile();
  if (!file || !importPreview) {
    setMessage("Analizza il file prima di confermare.", "warning");
    return;
  }
  if (document.body.dataset.workspaceState === "DEMO") {
    document.dispatchEvent(new CustomEvent("workspace:import-requested", {
      detail: { opener: byId("workforceConfirmBtn") },
    }));
    return;
  }
  importing = true;
  setBusy("import");
  byId("workforceImportState").innerHTML = `
    <div class="workforce-import-loading" aria-live="polite">
      <strong>Importazione del planning turni in corso...</strong>
      <span class="skeleton-line" aria-hidden="true"></span>
    </div>
  `;
  try {
    await confirmWorkforceImport(file, importPreview.fingerprint);
    importing = false;
    setBusy();
    close({ reset: true });
    await afterImport();
    setMessage("Planning turni importato.", "success");
  } catch (error) {
    const message = presentError("workforce.import", error);
    byId("workforceImportState").innerHTML = `
      <p class="import-notice blocking"><strong>Importazione non riuscita.</strong> ${message}</p>
    `;
  } finally {
    importing = false;
    setBusy();
  }
}


async function open(file = null, { analyzeFile = false } = {}) {
  if (analyzing || importing) return;
  resetPanel();
  routedFile = file;
  byId("workforceImportPanel").hidden = false;
  if (routedFile) {
    byId("workforceImportState").innerHTML = `
      <p class="import-notice ok"><strong>Planning turni riconosciuto.</strong>
      Il file selezionato e pronto per l'analisi.</p>
    `;
  }
  byId("workforceImportPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  if (analyzeFile && file) await analyze();
}


export function initWorkforceImportFlow({ onImported }) {
  afterImport = onImported;
  byId("workforceImportToggle").addEventListener("click", () => open());
  byId("workforceImportClose").addEventListener("click", () => close());
  byId("workforceAnalyzeBtn").addEventListener("click", analyze);
  byId("workforceImportForm").addEventListener("submit", confirm);
  return { open, reset: resetPanel };
}

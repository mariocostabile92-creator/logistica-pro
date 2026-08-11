import {
  confirmWorkforceImport,
  previewWorkforceImport,
} from "../api.js?v=5";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import {
  clearWorkforceImportPreview,
  renderWorkforceImportPreview,
} from "./workforce-view.js";
import { createWorkforceSurface } from "./workforce-surface.js";


let routedFile = null;
let importPreview = null;
let analyzing = false;
let importing = false;
let afterImport = async () => {};
let notifySuccess = (message) => setMessage(message, "success");
let importSurface = null;
let progressTimer = null;


const PROGRESS_STAGES = Object.freeze({
  analysis: [
    "Lettura file",
    "Analisi fogli",
    "Preparazione anteprima",
  ],
  import: [
    "Verifica analisi",
    "Preparazione risorse",
    "Preparazione calendario",
    "Salvataggio",
    "Verifica finale",
  ],
});


function selectedFile() {
  return byId("workforceFile").files[0] || routedFile;
}


function presentError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
  return presentation.message;
}


function renderProgress(title, stages, activeIndex) {
  byId("workforceImportState").innerHTML = `
    <div class="workforce-import-progress" aria-live="polite">
      <strong>${title}</strong>
      <span>Fasi di elaborazione del file</span>
      <ol>
        ${stages.map((stage, index) => `
          <li class="${index < activeIndex ? "complete" : index === activeIndex ? "active" : "pending"}">
            ${stage}
          </li>
        `).join("")}
      </ol>
    </div>
  `;
}


function startProgress(kind) {
  const stages = PROGRESS_STAGES[kind];
  let activeIndex = 0;
  window.clearInterval(progressTimer);
  renderProgress(
    kind === "analysis" ? "Analisi del planning turni" : "Importazione del planning turni",
    stages,
    activeIndex,
  );
  progressTimer = window.setInterval(() => {
    if (activeIndex >= stages.length - 1) return;
    activeIndex += 1;
    renderProgress(
      kind === "analysis" ? "Analisi del planning turni" : "Importazione del planning turni",
      stages,
      activeIndex,
    );
  }, kind === "analysis" ? 650 : 450);
}


function stopProgress() {
  window.clearInterval(progressTimer);
  progressTimer = null;
}


function resetPanel() {
  stopProgress();
  importPreview = null;
  routedFile = null;
  byId("workforceFile").value = "";
  byId("workforceConfirmBtn").disabled = true;
  clearWorkforceImportPreview();
  delete byId("workforceImportPanel").dataset.importState;
}


function close({ reset = false } = {}) {
  if (analyzing || importing) return;
  importSurface.hide();
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
  startProgress("analysis");
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
    stopProgress();
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
  startProgress("import");
  try {
    const result = await confirmWorkforceImport(file, importPreview.fingerprint);
    const confirmedPreview = importPreview;
    importing = false;
    setBusy();
    close({ reset: true });
    await afterImport(result, confirmedPreview);
    notifySuccess(
      `Aggiornamento completato: ${result.members_created + result.members_updated} risorse, `
      + `${result.statuses_created + result.statuses_updated} stati.`,
    );
  } catch (error) {
    const message = presentError("workforce.import", error);
    byId("workforceImportState").innerHTML = `
      <p class="import-notice blocking"><strong>Importazione non riuscita.</strong> ${message}</p>
    `;
  } finally {
    stopProgress();
    importing = false;
    setBusy();
  }
}


async function open(file = null, { analyzeFile = false } = {}) {
  if (analyzing || importing) return;
  resetPanel();
  routedFile = file;
  importSurface.show(byId("workforceFile"));
  if (routedFile) {
    byId("workforceImportState").innerHTML = `
      <p class="import-notice ok"><strong>Planning turni riconosciuto.</strong>
      Il file selezionato e pronto per l'analisi.</p>
    `;
  }
  if (analyzeFile && file) await analyze();
}


export function initWorkforceImportFlow({ onImported, onSuccess }) {
  afterImport = onImported;
  notifySuccess = onSuccess || notifySuccess;
  importSurface = createWorkforceSurface({
    surface: byId("workforceImportPanel"),
    backdrop: byId("workforceImportBackdrop"),
    canClose: () => !analyzing && !importing,
    lockScroll: true,
  });
  byId("workforceImportToggle").addEventListener("click", () => open());
  byId("workforceImportClose").addEventListener("click", () => close());
  byId("workforceAnalyzeBtn").addEventListener("click", analyze);
  byId("workforceImportForm").addEventListener("submit", confirm);
  return { open, reset: resetPanel };
}

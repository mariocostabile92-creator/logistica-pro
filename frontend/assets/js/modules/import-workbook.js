import { importDataset, previewImport } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import {
  collectMapping,
  renderIssues,
  renderMapping,
  renderPreview,
  renderProfile,
  renderSheets,
} from "./import-preview.js";


function numericHeaderRow(input) {
  const value = Number(input.value);
  return Number.isInteger(value) && value > 0 ? value : null;
}


function requestOptions(elements, includeMapping = true) {
  return {
    sheetName: elements.sheet.value,
    headerRow: numericHeaderRow(elements.header),
    columnMapping: includeMapping
      ? collectMapping(elements.mapping)
      : [],
  };
}


function setStatus(elements, label, tone = "") {
  elements.status.textContent = label;
  elements.status.className = `tag ${tone}`.trim();
}


function showImportError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


function clearOutput(elements) {
  elements.profile.replaceChildren();
  elements.issues.replaceChildren();
  elements.mapping.replaceChildren();
  elements.preview.replaceChildren();
}


export function initWorkbookImport({
  datasetType,
  prefix,
  fileMissingMessage,
  importedEventType,
  stateKey,
}) {
  const elements = {
    form: byId(`${prefix}Form`),
    previewButton: byId(`${prefix}PreviewBtn`),
    resetButton: byId(`${prefix}ResetBtn`),
    file: byId(`${prefix}File`),
    sheet: byId(`${prefix}Sheet`),
    header: byId(`${prefix}HeaderRow`),
    status: byId(`${prefix}State`),
    profile: byId(`${prefix}Profile`),
    issues: byId(`${prefix}Issues`),
    mapping: byId(`${prefix}Mapping`),
    preview: byId(`${prefix}Preview`),
  };
  elements.submit = elements.form.querySelector('button[type="submit"]');
  let analyzed = false;
  let importAllowed = false;

  function setAnalyzedState({ ready = false, allowed = false } = {}) {
    analyzed = ready;
    importAllowed = ready && allowed;
    elements.submit.disabled = !importAllowed;
    elements.submit.title = importAllowed
      ? ""
      : "Analizza il file e risolvi i controlli bloccanti.";
  }

  function markStale() {
    if (!analyzed) return;
    setAnalyzedState();
    setStatus(elements, "Da rianalizzare", "warning");
    elements.previewButton.textContent = "Rianalizza";
    elements.previewButton.dataset.label = "Rianalizza";
  }

  function markStructureStale() {
    if (!analyzed) return;
    elements.mapping.replaceChildren();
    markStale();
  }

  function resetImport() {
    elements.form.reset();
    elements.sheet.innerHTML = '<option value="">Automatico</option>';
    clearOutput(elements);
    setAnalyzedState();
    setStatus(elements, "In attesa");
    elements.previewButton.textContent = "Analizza file";
    elements.previewButton.dataset.label = "Analizza file";
    state[stateKey].imported = false;
    state[stateKey].rows = [];
    if (stateKey === "planning") state.planning.validImport = false;
  }

  async function analyze() {
    if (!elements.file.files.length) {
      setMessage(fileMissingMessage, "warning");
      return;
    }
    setLoading(elements.previewButton, true, "Analisi...");
    elements.submit.disabled = true;
    try {
      const data = await previewImport(
        elements.file.files[0],
        datasetType,
        requestOptions(elements),
      );
      renderSheets(elements.sheet, data.available_sheets, data.selected_sheet);
      elements.header.placeholder = data.selected_header_row
        ? `Rilevata: ${data.selected_header_row}`
        : "Non rilevata";
      renderProfile(elements.profile, data);
      renderIssues(elements.issues, data.blocking_reasons, data.warnings);
      const typeMismatch = data.blocking_reasons.some(
        (item) => item.code === "WORKBOOK_TYPE_MISMATCH",
      );
      renderMapping(
        elements.mapping,
        data.column_mappings,
        data.mapping_options,
        { disabled: typeMismatch },
      );
      renderPreview(elements.preview, data.sample_rows);
      setAnalyzedState({ ready: true, allowed: data.import_allowed });
      setStatus(
        elements,
        data.import_allowed ? "Pronto all'import" : "Verifica necessaria",
        data.import_allowed ? "ok" : "warning",
      );
      elements.previewButton.textContent = "Rianalizza";
      elements.previewButton.dataset.label = "Rianalizza";
      setMessage("");
    } catch (error) {
      setAnalyzedState();
      setStatus(elements, "Analisi non riuscita", "error");
      showImportError(`imports.preview-${datasetType}`, error);
    } finally {
      setLoading(elements.previewButton, false);
    }
  }

  elements.previewButton.addEventListener("click", analyze);
  elements.file.addEventListener("change", () => {
    clearOutput(elements);
    setAnalyzedState();
    setStatus(elements, "Da analizzare");
    elements.sheet.innerHTML = '<option value="">Automatico</option>';
    elements.header.value = "";
    elements.header.placeholder = "Automatico";
    elements.previewButton.textContent = "Analizza file";
    elements.previewButton.dataset.label = "Analizza file";
  });
  elements.sheet.addEventListener("change", markStructureStale);
  elements.header.addEventListener("input", markStructureStale);
  elements.mapping.addEventListener("change", markStale);
  elements.resetButton.addEventListener("click", resetImport);

  elements.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!elements.file.files.length) {
      setMessage(fileMissingMessage, "warning");
      return;
    }
    if (!analyzed || !importAllowed) {
      setMessage(
        "Rianalizza il file e risolvi i controlli prima dell'import.",
        "warning",
      );
      return;
    }
    if (document.body.dataset.workspaceState === "DEMO") {
      document.dispatchEvent(new CustomEvent("workspace:import-requested", {
        detail: { opener: elements.submit },
      }));
      return;
    }
    setLoading(elements.submit, true, "Import...");
    try {
      const data = await importDataset(
        elements.file.files[0],
        datasetType,
        requestOptions(elements),
      );
      state[stateKey].imported = true;
      state[stateKey].rows = data.normalized_rows;
      if (stateKey === "planning") state.planning.validImport = true;
      setStatus(elements, `${data.rows_imported} righe importate`, "ok");
      document.dispatchEvent(new CustomEvent("operations:data-imported", {
        detail: { datasetType: importedEventType },
      }));
      setMessage("");
    } catch (error) {
      setStatus(elements, "Import non riuscito", "error");
      showImportError(`imports.${datasetType}`, error);
    } finally {
      setLoading(elements.submit, false);
      elements.submit.disabled = !importAllowed;
    }
  });

  document.addEventListener("workspace:reset-completed", resetImport);
  setAnalyzedState();
}

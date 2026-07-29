import { importDataset, previewImport } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { renderMapping, renderPreview, renderSheets } from "./import-preview.js";


export function initPlanningImport() {
  const form = byId("planningForm");
  const previewBtn = byId("planningPreviewBtn");
  const fileInput = byId("planningFile");
  const sheetSelect = byId("planningSheet");
  const status = byId("planningState");

  previewBtn.addEventListener("click", async () => {
    if (!fileInput.files.length) return setMessage("Seleziona un file planning.");
    setLoading(previewBtn, true, "Lettura...");
    try {
      const data = await previewImport(fileInput.files[0], "planning", sheetSelect.value);
      renderSheets(sheetSelect, data.sheets, data.selected_sheet);
      renderMapping(byId("planningMapping"), data.recognized_columns, data.unrecognized_columns);
      renderPreview(byId("planningPreview"), data.preview_rows);
      status.textContent = "Preview pronta";
      status.className = "tag ok";
      setMessage("");
    } catch (error) {
      status.textContent = "Errore";
      status.className = "tag error";
      setMessage(error.message);
    } finally {
      setLoading(previewBtn, false);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!fileInput.files.length) return setMessage("Seleziona un file planning.");
    const submitBtn = form.querySelector('button[type="submit"]');
    setLoading(submitBtn, true, "Import...");
    try {
      const data = await importDataset(fileInput.files[0], "planning", sheetSelect.value);
      state.planning.imported = true;
      state.planning.rows = data.normalized_rows;
      status.textContent = `${data.rows_imported} righe importate`;
      status.className = "tag ok";
      renderMapping(byId("planningMapping"), data.mapping.filter((item) => item.target_field && !item.requires_confirmation), data.mapping.filter((item) => item.requires_confirmation || !item.target_field).map((item) => item.source_column));
      document.dispatchEvent(new CustomEvent("operations:data-imported", { detail: { datasetType: "planning" } }));
      setMessage("");
    } catch (error) {
      status.textContent = "Errore";
      status.className = "tag error";
      setMessage(error.message);
    } finally {
      setLoading(submitBtn, false);
    }
  });
}

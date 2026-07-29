import { importDataset, previewImport } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { renderMapping, renderPreview, renderSheets } from "./import-preview.js";


export function initFleetImport() {
  const form = byId("fleetForm");
  const previewBtn = byId("fleetPreviewBtn");
  const fileInput = byId("fleetFile");
  const sheetSelect = byId("fleetSheet");
  const status = byId("fleetState");

  previewBtn.addEventListener("click", async () => {
    if (!fileInput.files.length) return setMessage("Seleziona un file parco auto.");
    setLoading(previewBtn, true, "Lettura...");
    try {
      const data = await previewImport(fileInput.files[0], "fleet", sheetSelect.value);
      renderSheets(sheetSelect, data.sheets, data.selected_sheet);
      renderMapping(byId("fleetMapping"), data.recognized_columns, data.unrecognized_columns);
      renderPreview(byId("fleetPreview"), data.preview_rows);
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
    if (!fileInput.files.length) return setMessage("Seleziona un file parco auto.");
    const submitBtn = form.querySelector('button[type="submit"]');
    setLoading(submitBtn, true, "Import...");
    try {
      const data = await importDataset(fileInput.files[0], "fleet", sheetSelect.value);
      state.fleet.imported = true;
      state.fleet.rows = data.normalized_rows;
      status.textContent = `${data.rows_imported} righe importate`;
      status.className = "tag ok";
      renderMapping(byId("fleetMapping"), data.mapping.filter((item) => item.target_field && !item.requires_confirmation), data.mapping.filter((item) => item.requires_confirmation || !item.target_field).map((item) => item.source_column));
      document.dispatchEvent(new CustomEvent("operations:data-imported", { detail: { datasetType: "fleet" } }));
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

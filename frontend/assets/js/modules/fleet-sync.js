import { confirmFleetSync, previewFleetSync } from "../api.js?v=5";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import { renderFleetSyncDiff, renderFleetSyncSummary } from "./fleet-sync-view.js";


let routedFile = null;
let preview = null;
let activeFilter = "ALL";
let selectedRows = new Set();


function file() {
  return byId("fleetSyncFile").files[0] || routedFile;
}


function options() {
  const header = Number(byId("fleetSyncHeader").value || 0);
  return {
    sheetName: byId("fleetSyncSheet").value.trim(),
    headerRow: header > 0 ? header : null,
  };
}


function showError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


function open(fileValue = null) {
  routedFile = fileValue || routedFile;
  const panel = byId("fleetSyncPanel");
  if (!panel.open) panel.showModal();
  requestAnimationFrame(() => byId("fleetSyncFile").focus({ preventScroll: true }));
}


function renderDiff() {
  renderFleetSyncDiff(
    byId("fleetSyncDiff"),
    preview?.items || [],
    activeFilter,
    selectedRows,
  );
  byId("fleetSyncDiff").querySelectorAll("[data-fleet-sync-row]").forEach((input) => {
    input.addEventListener("change", () => {
      const rowId = Number(input.dataset.fleetSyncRow);
      if (input.checked) selectedRows.add(rowId);
      else selectedRows.delete(rowId);
      byId("fleetSyncConfirm").disabled = selectedRows.size === 0;
    });
  });
}


async function analyze() {
  const selectedFile = file();
  if (!selectedFile) {
    setMessage("Seleziona un file stato parco.", "warning");
    return;
  }
  setLoading(byId("fleetSyncAnalyze"), true, "Analisi...");
  byId("fleetSyncConfirm").disabled = true;
  try {
    preview = await previewFleetSync(selectedFile, options());
    selectedRows = new Set(
      preview.items.filter((item) => item.selected_by_default).map((item) => item.row_id),
    );
    byId("fleetSyncSheet").value = preview.selected_sheet;
    byId("fleetSyncHeader").value = preview.selected_header_row;
    byId("fleetSyncState").innerHTML = `
      <p class="import-notice ok"><strong>Registro Fleet riconosciuto.</strong>
      ${preview.profiled_sheets} fogli profilati, ${preview.source_rows} righe analizzate.
      I campi sensibili sono esclusi e non vengono mostrati.</p>
    `;
    renderFleetSyncSummary(preview.summary);
    renderDiff();
    byId("fleetSyncFilters").hidden = false;
    byId("fleetSyncConfirm").disabled = selectedRows.size === 0;
    setMessage("");
  } catch (error) {
    preview = null;
    byId("fleetSyncState").innerHTML = '<p class="import-notice blocking">Analisi Fleet non riuscita.</p>';
    showError("fleet.sync-preview", error);
  } finally {
    setLoading(byId("fleetSyncAnalyze"), false);
  }
}


async function confirm(event) {
  event.preventDefault();
  if (!preview || !file()) {
    setMessage("Analizza il registro Fleet prima di applicare le modifiche.", "warning");
    return;
  }
  if (document.body.dataset.workspaceState === "DEMO") {
    document.dispatchEvent(new CustomEvent("workspace:import-requested", {
      detail: { opener: byId("fleetSyncConfirm") },
    }));
    return;
  }
  const rowsToApply = [...selectedRows];
  if (!rowsToApply.length) {
    setMessage("Seleziona almeno una proposta applicabile.", "warning");
    return;
  }
  setLoading(byId("fleetSyncConfirm"), true, "Sincronizzazione...");
  try {
    const result = await confirmFleetSync(
      file(), preview.fingerprint, rowsToApply, options(),
    );
    byId("fleetSyncState").innerHTML = `
      <p class="import-notice ok"><strong>Asset Registry sincronizzato.</strong>
      ${result.created_assets} creati, ${result.updated_assets} aggiornati,
      ${result.events_created} eventi. ${result.idempotent ? "Nessuna duplicazione al reimport." : ""}</p>
    `;
    document.dispatchEvent(new CustomEvent("fleet:sync-completed", { detail: result }));
    document.dispatchEvent(new CustomEvent("operations:data-imported", {
      detail: { datasetType: "fleet" },
    }));
    byId("fleetSyncPanel").close();
    setMessage("Parco mezzi aggiornato.", "success");
    requestAnimationFrame(() => byId("fleetSearchInput").focus({ preventScroll: true }));
  } catch (error) {
    showError("fleet.sync-confirm", error);
  } finally {
    setLoading(byId("fleetSyncConfirm"), false);
  }
}


export function initFleetSync() {
  byId("fleetSyncToggle").addEventListener("click", () => open());
  byId("fleetSyncClose").addEventListener("click", () => {
    byId("fleetSyncPanel").close();
  });
  byId("fleetSyncAnalyze").addEventListener("click", analyze);
  byId("fleetSyncForm").addEventListener("submit", confirm);
  byId("fleetSyncFile").addEventListener("change", () => {
    routedFile = null;
    preview = null;
    selectedRows = new Set();
    byId("fleetSyncConfirm").disabled = true;
    byId("fleetSyncDiff").replaceChildren();
    byId("fleetSyncSummary").replaceChildren();
    byId("fleetSyncFilters").hidden = true;
  });
  byId("fleetSyncFilters").querySelectorAll("[data-fleet-sync-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.fleetSyncFilter;
      byId("fleetSyncFilters").querySelectorAll("button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderDiff();
    });
  });
  document.addEventListener("fleet:sync-requested", (event) => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "fleet", targetId: "fleetSyncPanel" },
    }));
    open(event.detail?.file || null);
    if (event.detail?.file) analyze();
  });
  document.addEventListener("workspace:reset-completed", () => {
    routedFile = null;
    preview = null;
    selectedRows = new Set();
    byId("fleetSyncForm").reset();
    if (byId("fleetSyncPanel").open) byId("fleetSyncPanel").close();
  });
}

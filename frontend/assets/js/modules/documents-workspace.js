import {
  createVehicleDocument,
  getVehicleDocument,
  listFleetAssets,
  listVehicleDocuments,
  updateVehicleDocument,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";
import { mountAttachments } from "./attachments/component.js";

const TYPES = {
  carta_circolazione: "Carta di circolazione",
  assicurazione: "Assicurazione",
  revisione: "Revisione",
  bollo: "Bollo",
  contratto_noleggio: "Contratto di noleggio",
  contratto_leasing: "Contratto di leasing",
  manuale: "Manuale",
  manutenzione: "Documento di manutenzione",
  altro: "Altro",
};
const STATUSES = {
  valido: "Valido",
  in_scadenza: "In scadenza",
  scaduto: "Scaduto",
  senza_scadenza: "Senza scadenza",
  mancante: "Mancante",
};
let records = [];
let selectedId = null;
let assetFilter = null;
let assets = [];

const root = () => document.getElementById("documentsWorkspace");
const date = (value) => value
  ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("it-IT")
  : "Senza scadenza";

function values(form) {
  const output = Object.fromEntries(new FormData(form).entries());
  output.vehicle_id = Number(output.vehicle_id);
  for (const key of ["document_number", "issuer", "issued_at", "expires_at", "notes"]) {
    output[key] ||= null;
  }
  output.file_name = null;
  output.file_reference = null;
  return output;
}

function renderSummary(summary) {
  for (const [key, value] of Object.entries(summary)) {
    const target = root().querySelector(`[data-doc-kpi="${key}"]`);
    if (target) target.textContent = value;
  }
}

function renderList() {
  const target = root().querySelector("#documentsList");
  const hasFilters = [
    "#documentsSearch", "#documentsStatus", "#documentsType", "#documentsFile",
  ].some((selector) => root().querySelector(selector).value);
  target.innerHTML = records.length ? records.map((item) => `
    <button type="button" class="document-card${Number(item.id) === Number(selectedId) ? " selected" : ""}"
      data-document-id="${item.id}" aria-current="${Number(item.id) === Number(selectedId)}">
      <span><strong>${escapeHtml(item.plate || item.external_identifier)}</strong><small>${escapeHtml(item.vehicle_model || "Mezzo")}</small></span>
      <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(TYPES[item.document_type])}</small></span>
      <span><small>Scadenza</small>${escapeHtml(date(item.expires_at))}</span>
      <span class="document-status status-${item.status}">${escapeHtml(STATUSES[item.status])}</span>
      <span><small>${escapeHtml(item.issuer || "Ente non indicato")}</small>${item.has_file ? "File presente" : "File mancante"}</span>
    </button>
  `).join("") : `<div class="documents-empty">${
    assetFilter ? "Nessun documento per il mezzo selezionato."
      : hasFilters ? "Nessun risultato per i filtri."
        : "Nessun documento registrato."
  }</div>`;
}

async function refresh(documentId = selectedId) {
  const search = root().querySelector("#documentsSearch").value.trim();
  const status = root().querySelector("#documentsStatus").value;
  const documentType = root().querySelector("#documentsType").value;
  const file = root().querySelector("#documentsFile").value;
  const response = await listVehicleDocuments({
    vehicle_id: assetFilter,
    search,
    status,
    document_type: documentType,
    has_file: file === "" ? null : file === "present",
  });
  records = response.items;
  renderSummary(response.summary);
  renderList();
  if (documentId && records.some((item) => Number(item.id) === Number(documentId))) {
    await renderDetail(documentId);
  }
}

function formFields(item = {}) {
  return `
    <label>Mezzo<select name="vehicle_id" required ${item.id ? "disabled" : ""}>${
      assets.map((asset) => `<option value="${asset.id}" ${
        Number(item.vehicle_id || assetFilter) === Number(asset.id) ? "selected" : ""
      }>${escapeHtml(asset.plate || asset.external_identifier)} · ${escapeHtml(asset.category || "Modello non indicato")} · #${asset.id}</option>`).join("")
    }</select></label>
    <label>Tipo documento<select name="document_type" required>${
      Object.entries(TYPES).map(([key, label]) => `<option value="${key}" ${item.document_type === key ? "selected" : ""}>${label}</option>`).join("")
    }</select></label>
    <label>Titolo<input name="title" required maxlength="240" value="${escapeHtml(item.title || "")}"></label>
    <label>Numero documento<input name="document_number" value="${escapeHtml(item.document_number || "")}"></label>
    <label>Ente o società<input name="issuer" value="${escapeHtml(item.issuer || "")}"></label>
    <label>Data emissione<input name="issued_at" type="date" value="${escapeHtml(item.issued_at || "")}"></label>
    <label>Data scadenza<input name="expires_at" type="date" value="${escapeHtml(item.expires_at || "")}"></label>
    <label>Stato<select name="status">${
      Object.entries(STATUSES).map(([key, label]) => `<option value="${key}" ${item.status === key ? "selected" : ""}>${label}</option>`).join("")
    }</select></label>
    <label class="document-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || "")}</textarea></label>`;
}

async function renderDetail(documentId) {
  const item = await getVehicleDocument(documentId);
  selectedId = Number(documentId);
  renderList();
  const workspace = root();
  workspace.classList.add("documents-detail-mode");
  workspace.querySelector("#documentsNavigator").classList.add("detail-open");
  workspace.querySelector("#documentsDetail").innerHTML = `
    <button type="button" class="quiet documents-mobile-back" data-documents-back>← Torna alla lista</button>
    <header class="documents-detail-header">
      <div><p class="eyebrow">${escapeHtml(TYPES[item.document_type])}</p><h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.plate || item.external_identifier)} · Documento #${item.id}</p></div>
      <span class="document-status status-${item.status}">${escapeHtml(STATUSES[item.status])}</span>
    </header>
    <dl class="documents-detail-grid">
      <div><dt>Mezzo</dt><dd>${escapeHtml(item.vehicle_model || "Non indicato")}</dd></div>
      <div><dt>Targa</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div>
      <div><dt>Numero</dt><dd>${escapeHtml(item.document_number || "Non indicato")}</dd></div>
      <div><dt>Società o ente</dt><dd>${escapeHtml(item.issuer || "Non indicato")}</dd></div>
      <div><dt>Emissione</dt><dd>${escapeHtml(date(item.issued_at))}</dd></div>
      <div><dt>Scadenza</dt><dd>${escapeHtml(date(item.expires_at))}</dd></div>
      <div class="document-detail-wide"><dt>Note</dt><dd>${escapeHtml(item.notes || "Nessuna nota")}</dd></div>
      ${item.contract_link ? `<div class="document-detail-wide"><dt>Profilo contrattuale collegato</dt><dd>${escapeHtml(item.contract_link.contract_type.replaceAll("_", " "))} · ${escapeHtml(item.contract_link.contract_number || "Numero non indicato")}</dd></div>` : ""}
    </dl>
    <div class="documents-actions"><button type="button" data-edit-document>Modifica metadati</button>
      <button type="button" class="secondary" data-open-vehicle="${item.vehicle_id}">Apri dossier mezzo</button></div>
    <div data-attachments></div>`;
  await mountAttachments(workspace.querySelector("[data-attachments]"), {
    entityType: "document", entityId: item.id,
  });
  workspace.querySelector("[data-documents-back]").addEventListener("click", () => {
    workspace.classList.remove("documents-detail-mode");
    workspace.querySelector("#documentsNavigator").classList.remove("detail-open");
  });
  workspace.querySelector("[data-edit-document]").addEventListener("click", () => openEditor(item));
  workspace.querySelector("[data-open-vehicle]").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("fleet:vehicle-open", {
      detail: { assetId: item.vehicle_id },
    }));
  });
}

function openEditor(item = {}) {
  const dialog = root().querySelector("#documentMetadataEditor");
  dialog.querySelector("h3").textContent = item.id ? "Modifica documento" : "Nuovo documento";
  dialog.querySelector("form").dataset.documentId = item.id || "";
  dialog.querySelector("[data-document-fields]").innerHTML = formFields(item);
  dialog.querySelector("[data-document-form-status]").textContent = "";
  dialog.showModal();
}

function shell() {
  const options = Object.entries(TYPES).map(([key, label]) => `<option value="${key}">${label}</option>`).join("");
  return `
    <header class="documents-header"><div><p class="eyebrow">Fleet Operations</p>
      <h2 id="documentsWorkspaceTitle">Documenti</h2><p>Archivio documentale del parco mezzi</p></div>
      <button type="button" data-new-document>Nuovo documento</button></header>
    <div class="documents-kpis" aria-label="Riepilogo documenti">
      <article><span>Documenti totali</span><strong data-doc-kpi="total">0</strong></article>
      <article><span>Documenti scaduti</span><strong data-doc-kpi="expired">0</strong></article>
      <article><span>In scadenza</span><strong data-doc-kpi="expiring">0</strong></article>
      <article><span>Mezzi senza documentazione</span><strong data-doc-kpi="assets_without_documents">0</strong></article>
      <article><span>File mancanti</span><strong data-doc-kpi="missing_files">0</strong></article>
    </div>
    <div class="documents-tools">
      <label><span class="visually-hidden">Cerca documenti</span><input id="documentsSearch" type="search" placeholder="Cerca targa, titolo, numero o società"></label>
      <select id="documentsStatus" aria-label="Filtra per stato"><option value="">Tutti gli stati</option>${Object.entries(STATUSES).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select>
      <select id="documentsType" aria-label="Filtra per tipo"><option value="">Tutti i tipi</option>${options}</select>
      <select id="documentsFile" aria-label="Filtra per presenza file"><option value="">Tutti i file</option><option value="present">File presenti</option><option value="missing">File mancanti</option></select>
    </div>
    <div id="documentsNavigator" class="documents-navigator">
      <aside class="documents-list-pane" aria-label="Lista documenti"><div id="documentsList" class="documents-list"></div></aside>
      <div id="documentsDetail" class="documents-detail-pane"><div class="documents-empty"><strong>Seleziona un documento</strong><p>Apri un documento per consultarne i metadati.</p></div></div>
    </div>
    <dialog id="documentMetadataEditor" class="assignment-editor fleet-dialog">
      <form><div class="editor-heading"><div><p class="eyebrow">Archivio mezzo</p><h3>Nuovo documento</h3></div>
      <button type="button" class="icon-button" data-close-documents aria-label="Chiudi">&times;</button></div>
      <div class="document-form" data-document-fields></div>
      <p data-document-form-status role="status"></p>
      <div class="editor-actions"><button type="button" class="secondary" data-close-documents>Annulla</button><button type="submit">Salva documento</button></div>
      </form>
    </dialog>`;
}

export async function showDocumentsWorkspace({ vehicleId = null, documentId = null } = {}) {
  const workspace = root();
  ["damageWorkspace", "maintenanceWorkspace", "fleetWorkspaceHome", "fleetVehicleDossier"]
    .forEach((id) => { document.getElementById(id).hidden = true; });
  document.getElementById("franchiseWorkspace").hidden = true;
  document.getElementById("insuranceWorkspace").hidden = true;
  document.getElementById("rentalWorkspace").hidden = true;
  workspace.hidden = false;
  assetFilter = vehicleId ? Number(vehicleId) : null;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    workspace.querySelector("#documentsList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-document-id]");
      if (target) renderDetail(Number(target.dataset.documentId));
    });
    workspace.querySelectorAll("#documentsSearch, #documentsStatus, #documentsType, #documentsFile")
      .forEach((control) => control.addEventListener(
        control.id === "documentsSearch" ? "input" : "change",
        () => refresh(),
      ));
    workspace.querySelector("[data-new-document]").addEventListener("click", () => openEditor());
    workspace.querySelectorAll("[data-close-documents]").forEach((button) => {
      button.addEventListener("click", () => workspace.querySelector("#documentMetadataEditor").close());
    });
    workspace.querySelector("#documentMetadataEditor form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = Number(event.currentTarget.dataset.documentId || 0);
      const payload = values(event.currentTarget);
      if (id) {
        delete payload.vehicle_id;
        delete payload.file_name;
        delete payload.file_reference;
      }
      try {
        const saved = id
          ? await updateVehicleDocument(id, payload)
          : await createVehicleDocument(payload);
        workspace.querySelector("#documentMetadataEditor").close();
        await refresh(saved.id);
      } catch (error) {
        workspace.querySelector("[data-document-form-status]").textContent = error.message;
      }
    });
  }
  const assetResponse = await listFleetAssets();
  assets = assetResponse.items;
  await refresh(documentId);
}

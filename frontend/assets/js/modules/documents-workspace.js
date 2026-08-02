import {
  archiveVehicleDocument, createVehicleDocument, getVehicleDocument,
  listFleetAssets, listVehicleDocuments, updateVehicleDocument,
} from "../api.js";
import { can } from "../auth/state.js";
import { escapeHtml } from "../utils/dom.js";
import { mountAttachments } from "./attachments/component.js";
import { createAttachmentDraft } from "./attachments/draft-uploader.js";
import { saveEntityWithAttachments } from "./attachments/entity-adapter.js";
import { applyDocumentFilters } from "./documents/filters.js";
import {
  DOCUMENT_STATUSES, DOCUMENT_TYPES, documentStatusLabel,
  documentTypeLabel, validityExplanation,
} from "./documents/status-presenter.js";

let records = [];
let selectedId = null;
let assetFilter = null;
let assets = [];
let documentDraft = null;
let kpiMode = "";
let deadlineFilterIds = null;

const root = () => document.getElementById("documentsWorkspace");
const formatDate = (value, emptyLabel = "Senza scadenza") => value
  ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("it-IT")
  : emptyLabel;
const formatDateTime = value => value ? new Date(value).toLocaleString("it-IT") : "Non disponibile";

function values(form) {
  const output = Object.fromEntries(new FormData(form).entries());
  output.vehicle_id = Number(output.vehicle_id);
  for (const key of ["document_number", "issuer", "issued_at", "expires_at", "notes"]) output[key] ||= null;
  output.file_name = null;
  output.file_reference = null;
  return output;
}

function renderSummary(summary) {
  Object.entries(summary).forEach(([key, value]) => {
    const target = root().querySelector(`[data-doc-kpi="${key}"]`);
    if (target) target.textContent = value;
  });
  root().querySelectorAll("[data-doc-kpi-filter]").forEach(button => {
    button.classList.toggle("selected", button.dataset.docKpiFilter === kpiMode);
    button.setAttribute("aria-pressed", String(button.dataset.docKpiFilter === kpiMode));
  });
}

function activeFilters() {
  return ["#documentsSearch", "#documentsVehicle", "#documentsStatus", "#documentsType", "#documentsFile", "#documentsExpiry"]
    .some(selector => root().querySelector(selector)?.value)
    || Boolean(kpiMode) || Boolean(deadlineFilterIds);
}

function renderList() {
  const target = root().querySelector("#documentsList");
  target.innerHTML = records.length ? records.map(item => `
    <article class="document-card${Number(item.id) === Number(selectedId) ? " selected" : ""}">
      <button type="button" data-document-id="${item.id}" aria-current="${Number(item.id) === Number(selectedId)}">
        <span class="document-card-identity"><strong>${escapeHtml(item.plate || item.external_identifier)}</strong><small>${escapeHtml(documentTypeLabel(item.document_type))}</small></span>
        <span class="document-card-title"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.document_number || "Numero non indicato")}</small></span>
        <span><small>Scadenza</small>${escapeHtml(formatDate(item.expires_at))}</span>
        <span class="document-status status-${item.status}">${escapeHtml(documentStatusLabel(item.status))}</span>
        <span><small>Allegati</small>${Number(item.attachment_count || 0)}</span>
        <span><small>Aggiornato</small>${escapeHtml(formatDateTime(item.updated_at))}</span>
        <span class="document-open-label">Apri dettaglio →</span>
      </button>
    </article>`).join("") : `<div class="documents-empty"><strong>${
      kpiMode === "assets_without_documents" ? "Mezzi senza documentazione" : activeFilters() ? "Nessun risultato" : "Nessun documento registrato"
    }</strong><p>${kpiMode === "assets_without_documents"
      ? "Il contatore segnala i mezzi privi di record. Apri il dossier di un mezzo per registrarne il primo documento."
      : activeFilters() ? "Modifica o azzera i filtri per ampliare la ricerca." : "Registra il primo documento e allega il file sorgente."}</p></div>`;
}

async function refresh(documentId = selectedId) {
  const workspace = root();
  workspace.querySelector("#documentsList").innerHTML = '<p class="documents-loading" role="status">Caricamento documenti…</p>';
  const kpiStatus = kpiMode === "complete" ? "completo" : kpiMode;
  const status = kpiStatus && kpiStatus !== "total" && kpiStatus !== "assets_without_documents"
    ? kpiStatus : workspace.querySelector("#documentsStatus").value;
  const fileMode = workspace.querySelector("#documentsFile").value;
  const vehicle = workspace.querySelector("#documentsVehicle").value || assetFilter;
  try {
    const response = await listVehicleDocuments({
      vehicle_id: vehicle || null,
      search: workspace.querySelector("#documentsSearch").value.trim(),
      status,
      document_type: workspace.querySelector("#documentsType").value,
      has_file: fileMode === "" ? null : fileMode === "present",
    });
    const sourceItems = deadlineFilterIds
      ? response.items.filter(item => deadlineFilterIds.has(Number(item.id)))
      : response.items;
    records = kpiMode === "assets_without_documents" ? [] : applyDocumentFilters(sourceItems, {
      expiry: workspace.querySelector("#documentsExpiry").value,
      sort: workspace.querySelector("#documentsSort").value,
    });
    renderSummary(response.summary);
    renderList();
    if (documentId && records.some(item => Number(item.id) === Number(documentId))) await renderDetail(documentId);
  } catch (error) {
    workspace.querySelector("#documentsList").innerHTML = `<div class="documents-error" role="alert"><strong>Documenti non disponibili</strong><p>${escapeHtml(error.message)}</p><button type="button" data-documents-retry>Riprova</button></div>`;
    workspace.querySelector("[data-documents-retry]")?.addEventListener("click", () => refresh(documentId), { once: true });
  }
}

function formFields(item = {}) {
  return `
    <label>Mezzo<select name="vehicle_id" required ${item.id ? "disabled" : ""}>${assets.map(asset => `<option value="${asset.id}" ${Number(item.vehicle_id || assetFilter) === Number(asset.id) ? "selected" : ""}>${escapeHtml(asset.plate || asset.external_identifier)} · ${escapeHtml(asset.category || "Modello non indicato")}</option>`).join("")}</select></label>
    <label>Tipologia<select name="document_type" required>${Object.entries(DOCUMENT_TYPES).map(([key, label]) => `<option value="${key}" ${item.document_type === key ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label>Titolo o descrizione<input name="title" required maxlength="240" value="${escapeHtml(item.title || "")}"></label>
    <label>Numero documento<input name="document_number" value="${escapeHtml(item.document_number || "")}"></label>
    <label>Ente o soggetto emittente<input name="issuer" value="${escapeHtml(item.issuer || "")}"></label>
    <label>Data emissione<input name="issued_at" type="date" value="${escapeHtml(item.issued_at || "")}"></label>
    <label>Data scadenza<input name="expires_at" type="date" value="${escapeHtml(item.expires_at || "")}"></label>
    <label class="document-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || "")}</textarea></label>`;
}

const historyLabel = action => ({
  "document.created": "Documento creato", "document.updated": "Metadati aggiornati",
  "document.archived": "Documento archiviato", "attachment.added": "Allegato aggiunto",
  "attachment.removed": "Allegato rimosso",
}[action] || "Attività amministrativa");

async function renderDetail(documentId) {
  const item = await getVehicleDocument(documentId);
  selectedId = Number(documentId);
  renderList();
  const workspace = root();
  workspace.classList.add("documents-detail-mode");
  workspace.querySelector("#documentsNavigator").classList.add("detail-open");
  workspace.querySelector("#documentsDetail").innerHTML = `
    <button type="button" class="quiet documents-mobile-back" data-documents-back>← Torna alla lista</button>
    <header class="documents-detail-header"><div><p class="eyebrow">${escapeHtml(documentTypeLabel(item.document_type))}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.plate || item.external_identifier)} · Record #${item.id}</p></div><span class="document-status status-${item.status}">${escapeHtml(documentStatusLabel(item.status))}</span></header>
    <section class="document-detail-section"><h4>Documento</h4><dl class="documents-detail-grid">
      <div><dt>Tipologia</dt><dd>${escapeHtml(documentTypeLabel(item.document_type))}</dd></div><div><dt>Numero</dt><dd>${escapeHtml(item.document_number || "Non indicato")}</dd></div>
      <div><dt>Ente</dt><dd>${escapeHtml(item.issuer || "Non indicato")}</dd></div><div><dt>Emissione</dt><dd>${escapeHtml(formatDate(item.issued_at, "Non indicata"))}</dd></div>
      <div class="document-detail-wide"><dt>Note</dt><dd>${escapeHtml(item.notes || "Nessuna nota")}</dd></div></dl></section>
    <section class="document-detail-section"><h4>Veicolo</h4><dl class="documents-detail-grid"><div><dt>Targa</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div><div><dt>Modello</dt><dd>${escapeHtml(item.vehicle_model || "Non indicato")}</dd></div></dl><button type="button" class="secondary" data-open-vehicle="${item.vehicle_id}">Apri dossier mezzo</button></section>
    <section class="document-detail-section"><h4>Validità</h4><div class="document-validity"><span class="document-status status-${item.status}">${escapeHtml(documentStatusLabel(item.status))}</span><strong>${escapeHtml(formatDate(item.expires_at))}</strong><p>${escapeHtml(validityExplanation(item))}</p>${item.days_to_expiry == null ? "" : `<p><strong>${Math.abs(item.days_to_expiry)} giorni</strong> ${item.days_to_expiry < 0 ? "trascorsi dalla scadenza" : "alla scadenza"}.</p>`}</div></section>
    <section class="document-detail-section"><h4>Allegati</h4><div data-attachments></div></section>
    <section class="document-detail-section"><h4>Storico</h4><ol class="document-history">${item.history?.length ? item.history.map(event => `<li><strong>${escapeHtml(historyLabel(event.action))}</strong><span>${escapeHtml(formatDateTime(event.created_at))}${event.actor_user_id ? ` · Utente ${escapeHtml(event.actor_user_id)}` : ""}</span></li>`).join("") : "<li>Nessuna attività registrata.</li>"}</ol></section>
    <section class="document-detail-section"><h4>Azioni</h4><div class="documents-actions">
      ${can("documents:write") ? '<button type="button" data-edit-document>Modifica metadati</button>' : ""}
      <button type="button" class="secondary" data-open-vehicle="${item.vehicle_id}">Apri Vehicle Library</button>
      ${can("documents:archive") && item.status !== "archiviato" ? '<button type="button" class="quiet" data-archive-document>Archivia</button>' : ""}
    </div></section>`;
  await mountAttachments(workspace.querySelector("[data-attachments]"), {
    entityType: "document", entityId: item.id, readOnly: !can("attachments:write"),
    accept: ".pdf,.jpg,.jpeg,.png,.webp",
    emptyMessage: "Nessun file allegato: il documento risulta File mancante.",
    onChange: () => refresh(item.id),
  });
  workspace.querySelector("[data-documents-back]").addEventListener("click", () => {
    workspace.classList.remove("documents-detail-mode");
    workspace.querySelector("#documentsNavigator").classList.remove("detail-open");
  });
  workspace.querySelector("[data-edit-document]")?.addEventListener("click", () => openEditor(item));
  workspace.querySelectorAll("[data-open-vehicle]").forEach(button => button.addEventListener("click", () => document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: item.vehicle_id } }))));
  workspace.querySelector("[data-archive-document]")?.addEventListener("click", async () => {
    if (!window.confirm("Archiviare questo documento? Il record resterà nello storico.")) return;
    await archiveVehicleDocument(item.id);
    selectedId = null;
    workspace.querySelector("#documentsDetail").innerHTML = '<div class="documents-empty"><strong>Documento archiviato</strong><p>Il record resta consultabile selezionando il filtro Archiviato.</p></div>';
    await refresh();
  });
}

function openEditor(item = {}) {
  const dialog = root().querySelector("#documentMetadataEditor");
  dialog.querySelector("h3").textContent = item.id ? "Modifica documento" : "Nuovo documento";
  dialog.querySelector("form").dataset.documentId = item.id || "";
  dialog.querySelector("[data-document-fields]").innerHTML = formFields(item);
  dialog.querySelector("[data-document-form-status]").textContent = "";
  documentDraft.reset();
  dialog.showModal();
}

function shell() {
  const typeOptions = Object.entries(DOCUMENT_TYPES).map(([key, label]) => `<option value="${key}">${label}</option>`).join("");
  return `<header class="documents-header"><div><p class="eyebrow">Fleet Operations</p><h2 id="documentsWorkspaceTitle">Documenti</h2><p>Controllo operativo della conformità documentale della flotta</p></div><button type="button" data-new-document>Nuovo documento</button></header>
    <div class="documents-kpis" aria-label="Snapshot documentale">${[
      ["total", "Totale documenti"], ["complete", "Completi"], ["missing_files", "File mancanti"],
      ["expiring", "In scadenza"], ["expired", "Scaduti"], ["assets_without_documents", "Mezzi incompleti"],
    ].map(([key, label]) => `<button type="button" data-doc-kpi-filter="${key}"><strong data-doc-kpi="${key}">0</strong><span>${label}</span></button>`).join("")}</div>
    <div class="documents-quick-filters" aria-label="Filtri rapidi">${[["", "Tutti"], ["complete", "Completi"], ["file_mancante", "File mancanti"], ["in_scadenza", "In scadenza"], ["scaduto", "Scaduti"]].map(([key, label]) => `<button type="button" class="quiet" data-doc-quick-filter="${key}">${label}</button>`).join("")}</div>
    <div class="documents-tools">
      <label><span>Cerca</span><input id="documentsSearch" type="search" placeholder="Targa, titolo, numero, ente o tipologia"></label>
      <label><span>Veicolo</span><select id="documentsVehicle"><option value="">Tutti i veicoli</option></select></label>
      <label><span>Tipologia</span><select id="documentsType"><option value="">Tutte le tipologie</option>${typeOptions}</select></label>
      <label><span>Stato</span><select id="documentsStatus"><option value="">Tutti gli stati</option>${Object.entries(DOCUMENT_STATUSES).map(([key, label]) => `<option value="${key}">${label}</option>`).join("")}</select></label>
      <label><span>Allegato</span><select id="documentsFile"><option value="">Tutti</option><option value="present">File presente</option><option value="missing">File mancante</option></select></label>
      <label><span>Scadenza</span><select id="documentsExpiry"><option value="">Tutte</option><option value="dated">Con scadenza</option><option value="undated">Senza scadenza</option><option value="expiring">Entro 30 giorni</option><option value="expired">Scadute</option></select></label>
      <label><span>Ordina</span><select id="documentsSort"><option value="expiry">Scadenza</option><option value="updated">Ultima modifica</option><option value="plate">Targa</option><option value="title">Titolo</option></select></label>
      <button type="button" class="secondary" data-reset-document-filters>Azzera filtri</button></div>
    <div id="documentsNavigator" class="documents-navigator"><aside class="documents-list-pane" aria-label="Elenco documenti"><div id="documentsList" class="documents-list"></div></aside><div id="documentsDetail" class="documents-detail-pane"><div class="documents-empty"><strong>Seleziona un documento</strong><p>Apri il dettaglio per controllare validità, allegati e storico.</p></div></div></div>
    <dialog id="documentMetadataEditor" class="assignment-editor fleet-dialog" aria-labelledby="documentEditorTitle"><form><div class="editor-heading"><div><p class="eyebrow">Documenti flotta</p><h3 id="documentEditorTitle">Nuovo documento</h3></div><button type="button" class="icon-button" data-close-documents aria-label="Chiudi">&times;</button></div><div class="document-form" data-document-fields></div><div data-document-attachment-draft></div><p data-document-form-status role="status" aria-live="polite"></p><div class="editor-actions"><button type="button" class="secondary" data-close-documents>Annulla</button><button type="submit">Salva documento</button></div></form></dialog>`;
}

export async function showDocumentsWorkspace({
  vehicleId = null, documentId = null, deadlineIds = null,
} = {}) {
  const workspace = root();
  ["damageWorkspace", "maintenanceWorkspace", "fleetWorkspaceHome", "fleetVehicleDossier", "franchiseWorkspace", "insuranceWorkspace", "rentalWorkspace"].forEach(id => { document.getElementById(id).hidden = true; });
  workspace.hidden = false;
  assetFilter = vehicleId ? Number(vehicleId) : null;
  deadlineFilterIds = Array.isArray(deadlineIds)
    ? new Set(deadlineIds.map(Number)) : null;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    documentDraft = createAttachmentDraft(workspace.querySelector("[data-document-attachment-draft]"), { title: "Allegati", accept: ".pdf,.jpg,.jpeg,.png,.webp" });
    workspace.querySelector("#documentsList").addEventListener("click", event => { const target = event.target.closest("[data-document-id]"); if (target) renderDetail(Number(target.dataset.documentId)); });
    workspace.querySelector(".documents-kpis").addEventListener("click", event => { const button = event.target.closest("[data-doc-kpi-filter]"); if (!button) return; kpiMode = button.dataset.docKpiFilter; refresh(); });
    workspace.querySelector(".documents-quick-filters").addEventListener("click", event => { const button = event.target.closest("[data-doc-quick-filter]"); if (!button) return; kpiMode = ""; workspace.querySelector("#documentsStatus").value = button.dataset.docQuickFilter; refresh(); });
    workspace.querySelectorAll("#documentsSearch, #documentsVehicle, #documentsStatus, #documentsType, #documentsFile, #documentsExpiry, #documentsSort").forEach(control => control.addEventListener(control.id === "documentsSearch" ? "input" : "change", () => { kpiMode = ""; refresh(); }));
    workspace.querySelector("[data-reset-document-filters]").addEventListener("click", () => { kpiMode = ""; workspace.querySelectorAll(".documents-tools input, .documents-tools select").forEach(control => { control.value = control.id === "documentsSort" ? "expiry" : ""; }); refresh(); });
    workspace.querySelector("[data-new-document]")?.addEventListener("click", () => openEditor());
    workspace.querySelectorAll("[data-close-documents]").forEach(button => button.addEventListener("click", () => workspace.querySelector("#documentMetadataEditor").close()));
    workspace.querySelector("#documentMetadataEditor form").addEventListener("submit", async event => {
      event.preventDefault();
      const submit = event.currentTarget.querySelector("[type='submit']");
      if (submit.disabled) return;
      submit.disabled = true;
      const id = Number(event.currentTarget.dataset.documentId || 0);
      const payload = values(event.currentTarget);
      if (id) { delete payload.vehicle_id; delete payload.file_name; delete payload.file_reference; }
      try {
        const saved = await saveEntityWithAttachments({ draft: documentDraft, entityType: "document", saveRecord: () => id ? updateVehicleDocument(id, payload) : createVehicleDocument(payload) });
        workspace.querySelector("#documentMetadataEditor").close();
        await refresh(saved.id);
      } catch (error) { workspace.querySelector("[data-document-form-status]").textContent = error.message; }
      finally { submit.disabled = false; }
    });
    workspace.querySelector("[data-document-attachment-draft]").addEventListener("attachments:retry", () => workspace.querySelector("#documentMetadataEditor form").requestSubmit());
  }
  const assetResponse = await listFleetAssets();
  assets = assetResponse.items;
  workspace.querySelector("[data-new-document]").hidden = !can("documents:write");
  const vehicleSelect = workspace.querySelector("#documentsVehicle");
  vehicleSelect.innerHTML = '<option value="">Tutti i veicoli</option>' + assets.map(asset => `<option value="${asset.id}">${escapeHtml(asset.plate || asset.external_identifier)}</option>`).join("");
  vehicleSelect.value = assetFilter || "";
  await refresh(documentId);
}

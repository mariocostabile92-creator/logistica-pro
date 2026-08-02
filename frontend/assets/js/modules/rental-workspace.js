import {
  createRental, getRental, listFleetAssets, listRentals, updateRental,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";
import { mountAttachments } from "./attachments/component.js";
import { createAttachmentDraft } from "./attachments/draft-uploader.js";
import { saveEntityWithAttachments } from "./attachments/entity-adapter.js";

const STATUS = {
  programmato: "Programmato", attivo: "Attivo", prorogato: "Prorogato",
  concluso: "Concluso", annullato: "Annullato",
};
const REASON = {
  manutenzione: "Manutenzione", danno: "Danno", fermo_tecnico: "Fermo tecnico",
  picco_operativo: "Picco operativo", altro: "Altro",
};
let records = [];
let assets = [];
let selectedId = null;
let vehicleFilter = null;
let originPreset = null;
let rentalDraft = null;
let deadlineFilterIds = null;
const root = () => document.getElementById("rentalWorkspace");
const date = (value) => value ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("it-IT") : "Non indicata";

function summary(values) {
  for (const [key, value] of Object.entries(values)) {
    const target = root().querySelector(`[data-rental-kpi="${key}"]`);
    if (target) target.textContent = value;
  }
}

function renderList() {
  root().querySelector("#rentalList").innerHTML = records.length ? records.map((item) => `
    <button type="button" class="rental-card${Number(item.id) === Number(selectedId) ? " selected" : ""}"
      data-rental-id="${item.id}" aria-current="${Number(item.id) === Number(selectedId)}">
      <span><small>Mezzo sostituito</small><strong>${escapeHtml(item.plate || item.external_identifier || "Necessità operativa")}</strong></span>
      <span><small>Mezzo sostitutivo</small><strong>${escapeHtml(item.replacement_vehicle)}</strong></span>
      <span><small>Società</small>${escapeHtml(item.rental_company)}</span>
      <span class="rental-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span>
      <span><small>Inizio</small>${escapeHtml(date(item.start_date))}</span>
      <span><small>Fine prevista</small>${escapeHtml(date(item.expected_end_date))}</span>
    </button>`).join("") : `<div class="rental-empty">${
      vehicleFilter ? "Nessun noleggio per il mezzo selezionato." : "Nessun noleggio registrato."
    }</div>`;
}

function fields(item = {}, preset = originPreset || {}) {
  const selectedVehicle = item.vehicle_id || preset.vehicle_id || vehicleFilter;
  return `
    <label>Mezzo sostituito<select name="vehicle_id" ${item.id ? "disabled" : ""}><option value="">Necessità operativa senza mezzo</option>${assets.map((asset) =>
      `<option value="${asset.id}" ${Number(selectedVehicle) === Number(asset.id) ? "selected" : ""}>${escapeHtml(asset.plate || asset.external_identifier)} · ${escapeHtml(asset.category || "Modello non indicato")}</option>`
    ).join("")}</select></label>
    <label>Mezzo sostitutivo<input name="replacement_vehicle" required value="${escapeHtml(item.replacement_vehicle || "")}"></label>
    <label>Società di noleggio<input name="rental_company" required value="${escapeHtml(item.rental_company || "")}"></label>
    <label>Numero contratto<input name="contract_number" value="${escapeHtml(item.contract_number || "")}"></label>
    <label>Data inizio<input name="start_date" type="date" required value="${escapeHtml(item.start_date || "")}"></label>
    <label>Fine prevista<input name="expected_end_date" type="date" required value="${escapeHtml(item.expected_end_date || "")}"></label>
    <label>Data conclusione<input name="end_date" type="date" value="${escapeHtml(item.end_date || "")}"></label>
    <label>Motivo<select name="reason">${Object.entries(REASON).map(([key,label]) =>
      `<option value="${key}" ${key === (item.reason || preset.reason || "altro") ? "selected" : ""}>${label}</option>`
    ).join("")}</select></label>
    <label>Stato<select name="status">${Object.entries(STATUS).map(([key,label]) =>
      `<option value="${key}" ${key === (item.status || "programmato") ? "selected" : ""}>${label}</option>`
    ).join("")}</select></label>
    <label class="rental-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || preset.notes || "")}</textarea></label>`;
}

function openEditor(item = {}, preset = originPreset || {}) {
  const dialog = root().querySelector("#rentalEditor");
  dialog.querySelector("h3").textContent = item.id ? "Modifica noleggio" : "Nuovo noleggio";
  dialog.querySelector("form").dataset.rentalId = item.id || "";
  dialog.querySelector("[data-rental-fields]").innerHTML = fields(item, preset);
  dialog.querySelector("[data-rental-form-status]").textContent = "";
  rentalDraft.reset();
  dialog.showModal();
}

async function detail(id) {
  const item = await getRental(id);
  selectedId = Number(id);
  renderList();
  const workspace = root();
  workspace.querySelector("#rentalNavigator").classList.add("detail-open");
  workspace.querySelector("#rentalDetail").innerHTML = `
    <button type="button" class="quiet rental-mobile-back" data-rental-back>← Torna alla lista</button>
    <header class="rental-detail-header"><div><p class="eyebrow">Noleggio</p><h3>${escapeHtml(item.replacement_vehicle)}</h3>
      <p>${escapeHtml(item.plate || item.external_identifier || "Necessità operativa")}</p></div>
      <span class="rental-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span></header>
    <dl class="rental-detail-grid">
      <div><dt>Mezzo originale</dt><dd>${escapeHtml(item.plate || item.external_identifier || "Non associato")}</dd></div>
      <div><dt>Mezzo sostitutivo</dt><dd>${escapeHtml(item.replacement_vehicle)}</dd></div>
      <div><dt>Motivo</dt><dd>${escapeHtml(REASON[item.reason])}</dd></div>
      <div><dt>Società</dt><dd>${escapeHtml(item.rental_company)}</dd></div>
      <div><dt>Contratto</dt><dd>${escapeHtml(item.contract_number || "Non indicato")}</dd></div>
      <div><dt>Periodo</dt><dd>${escapeHtml(date(item.start_date))} → ${escapeHtml(date(item.end_date || item.expected_end_date))}</dd></div>
      <div><dt>Pratica danno</dt><dd>${escapeHtml(item.damage_case_number || "Non collegata")}</dd></div>
      <div><dt>Manutenzione</dt><dd>${escapeHtml(item.maintenance_number || "Non collegata")}</dd></div>
      <div class="rental-detail-wide"><dt>Note</dt><dd>${escapeHtml(item.notes || "Nessuna nota")}</dd></div>
    </dl><button type="button" data-edit-rental>Modifica noleggio</button>
    <div data-attachments></div>`;
  await mountAttachments(workspace.querySelector("[data-attachments]"), {
    entityType: "rental", entityId: item.id,
  });
  workspace.querySelector("[data-rental-back]").addEventListener("click", () =>
    workspace.querySelector("#rentalNavigator").classList.remove("detail-open"));
  workspace.querySelector("[data-edit-rental]").addEventListener("click", () => openEditor(item));
}

async function refresh(id = selectedId) {
  const response = await listRentals({ vehicle_id: vehicleFilter });
  records = deadlineFilterIds
    ? response.items.filter(item => deadlineFilterIds.has(Number(item.id)))
    : response.items;
  summary(response.summary);
  renderList();
  if (id && records.some((item) => Number(item.id) === Number(id))) await detail(id);
}

function shell() {
  return `<header class="rental-header"><div><p class="eyebrow">Fleet Operations</p>
    <h2 id="rentalWorkspaceTitle">Noleggi</h2><p>Gestione dei veicoli sostitutivi</p></div>
    <button type="button" data-new-rental>Nuovo noleggio</button></header>
    <div class="rental-kpis" aria-label="Riepilogo noleggi">
      <article><span>Noleggi attivi</span><strong data-rental-kpi="active">0</strong></article>
      <article><span>Noleggi programmati</span><strong data-rental-kpi="scheduled">0</strong></article>
      <article><span>Noleggi conclusi</span><strong data-rental-kpi="completed">0</strong></article>
      <article><span>Mezzi sostituiti</span><strong data-rental-kpi="replaced_vehicles">0</strong></article>
    </div>
    <div id="rentalNavigator" class="rental-navigator"><aside class="rental-list-pane" aria-label="Lista noleggi"><div id="rentalList" class="rental-list"></div></aside>
    <div id="rentalDetail" class="rental-detail-pane"><div class="rental-empty"><strong>Seleziona un noleggio</strong><p>Apri un noleggio per consultarne il periodo.</p></div></div></div>
    <dialog id="rentalEditor" class="assignment-editor fleet-dialog"><form><div class="editor-heading">
      <div><p class="eyebrow">Veicolo sostitutivo</p><h3>Nuovo noleggio</h3></div><button type="button" class="icon-button" data-close-rental aria-label="Chiudi">&times;</button></div>
      <div class="rental-form" data-rental-fields></div>
      <div data-rental-attachment-draft></div><p data-rental-form-status role="status"></p>
      <div class="editor-actions"><button type="button" class="secondary" data-close-rental>Annulla</button><button type="submit">Salva noleggio</button></div></form></dialog>`;
}

export async function showRentalWorkspace({
  rentalId = null, vehicleId = null, preset = null, deadlineIds = null,
} = {}) {
  const workspace = root();
  ["damageWorkspace","maintenanceWorkspace","documentsWorkspace","franchiseWorkspace",
    "insuranceWorkspace","fleetWorkspaceHome","fleetVehicleDossier"].forEach((id) => {
    document.getElementById(id).hidden = true;
  });
  workspace.hidden = false;
  vehicleFilter = vehicleId ? Number(vehicleId) : null;
  deadlineFilterIds = Array.isArray(deadlineIds)
    ? new Set(deadlineIds.map(Number)) : null;
  originPreset = preset;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    rentalDraft = createAttachmentDraft(
      workspace.querySelector("[data-rental-attachment-draft]"),
      { title: "Contratto e allegati", accept: ".pdf,.jpg,.jpeg,.png,.webp" },
    );
    workspace.querySelector("#rentalList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-rental-id]");
      if (target) detail(Number(target.dataset.rentalId));
    });
    workspace.querySelector("[data-new-rental]").addEventListener("click", () => openEditor());
    workspace.querySelectorAll("[data-close-rental]").forEach((button) =>
      button.addEventListener("click", () => workspace.querySelector("#rentalEditor").close()));
    workspace.querySelector("#rentalEditor form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = event.currentTarget.querySelector("[type='submit']");
      if (submit.disabled) return;
      submit.disabled = true;
      const id = Number(event.currentTarget.dataset.rentalId || 0);
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      for (const field of ["vehicle_id","contract_number","end_date","notes"]) values[field] ||= null;
      if (values.vehicle_id) values.vehicle_id = Number(values.vehicle_id);
      if (!id && originPreset) Object.assign(values, {
        damage_case_id: originPreset.damage_case_id || null,
        maintenance_id: originPreset.maintenance_id || null,
      });
      if (id) delete values.vehicle_id;
      try {
        const saved = await saveEntityWithAttachments({
          draft: rentalDraft,
          entityType: "rental",
          saveRecord: () => id ? updateRental(id, values) : createRental(values),
        });
        workspace.querySelector("#rentalEditor").close();
        originPreset = null;
        await refresh(saved.id);
      } catch (error) {
        workspace.querySelector("[data-rental-form-status]").textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
    workspace.querySelector("[data-rental-attachment-draft]").addEventListener(
      "attachments:retry",
      () => workspace.querySelector("#rentalEditor form").requestSubmit(),
    );
  }
  assets = (await listFleetAssets()).items;
  await refresh(rentalId);
  if (preset) openEditor({}, preset);
}

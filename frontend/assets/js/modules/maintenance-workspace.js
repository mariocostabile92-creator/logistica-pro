import {
  createMaintenance,
  getMaintenance,
  listFleetAssets,
  listMaintenances,
  updateMaintenance,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";


const STATUS = Object.freeze({
  aperta: "Aperta",
  programmata: "Programmata",
  in_lavorazione: "In lavorazione",
  completata: "Completata",
  annullata: "Annullata",
});
const TYPE = Object.freeze({
  tagliando: "Tagliando",
  pneumatici: "Pneumatici",
  revisione: "Revisione",
  freni: "Freni",
  meccanica: "Meccanica",
  carrozzeria: "Carrozzeria",
  elettrico: "Elettrico",
  altro: "Altro",
});
const PRIORITY = Object.freeze({
  bassa: "Bassa",
  media: "Media",
  alta: "Alta",
  critica: "Critica",
});

const root = () => document.getElementById("maintenanceWorkspace");
let records = [];
let selectedId = null;

const date = (value) => {
  if (!value) return "Non registrata";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
};

function renderSummary(summary) {
  root().querySelector("#maintenanceOpen").textContent = summary.open;
  root().querySelector("#maintenanceWorkshop").textContent = summary.in_workshop;
  root().querySelector("#maintenanceScheduled").textContent = summary.scheduled;
  root().querySelector("#maintenanceCompleted").textContent = summary.completed;
}

function renderList() {
  const list = root().querySelector("#maintenanceList");
  if (!records.length) {
    list.innerHTML = `
      <div class="maintenance-empty">
        <strong>Nessuna manutenzione registrata</strong>
        <p>Le manutenzioni create dal Fleet Manager o da una pratica danno compariranno qui.</p>
      </div>`;
    return;
  }
  list.innerHTML = records.map((item) => `
    <button
      type="button"
      class="maintenance-card${Number(item.id) === Number(selectedId) ? " selected" : ""}"
      data-maintenance-id="${item.id}"
      aria-pressed="${Number(item.id) === Number(selectedId)}"
    >
      <span class="maintenance-card-heading">
        <strong>${escapeHtml(item.maintenance_number)}</strong>
        <span class="maintenance-status status-${escapeHtml(item.status)}">${escapeHtml(STATUS[item.status])}</span>
      </span>
      <span><small>Mezzo</small><strong>${escapeHtml(item.plate || item.external_identifier)}</strong></span>
      <span><small>Tipologia</small>${escapeHtml(TYPE[item.maintenance_type])}</span>
      <span><small>Priorità</small><span class="priority-${escapeHtml(item.priority)}">${escapeHtml(PRIORITY[item.priority])}</span></span>
      <span><small>Officina</small>${escapeHtml(item.repair_shop || "Da assegnare")}</span>
      <span><small>Apertura</small>${escapeHtml(date(item.opened_at))}</span>
    </button>
  `).join("");
}

function timeline(events) {
  return events.map((event) => `
    <li>
      <time>${escapeHtml(date(event.created_at))}</time>
      <strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong>
      <p>${escapeHtml(event.note || "")}</p>
      <small>${escapeHtml(event.actor)}</small>
    </li>
  `).join("");
}

function contractContext(profile) {
  if (!profile) return '<p>Profilo contrattuale non configurato.</p>';
  const types = {
    lungo_termine: "Lungo termine",
    breve_termine: "Breve termine",
    proprieta: "Proprietà",
    leasing: "Leasing",
    altro: "Altro",
  };
  const money = (value) => value == null
    ? "Non registrato"
    : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(value));
  const fields = [
    ["Tipo contratto", types[profile.contract_type]],
    ["Società", profile.company || profile.owner_company || "Non registrata"],
    ["Contratto", profile.contract_number || "Non registrato"],
  ];
  if (profile.contract_type === "lungo_termine") {
    fields.push(["Franchigia prevista", money(profile.deductible)]);
  }
  if (profile.contract_type === "breve_termine") {
    fields.push(["Costo giornaliero", money(profile.daily_cost)]);
    fields.push(["Costo fermo mezzo", "Non calcolato"]);
  }
  return `<dl>${fields.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>`;
}

async function renderDetail(maintenanceId) {
  const item = await getMaintenance(maintenanceId);
  selectedId = Number(maintenanceId);
  const workspace = root();
  workspace.classList.add("maintenance-detail-mode");
  renderList();
  workspace.querySelector("#maintenanceNavigator").classList.add("detail-open");
  workspace.querySelector("#maintenanceDetail").innerHTML = `
    <button type="button" class="quiet maintenance-mobile-back" data-maintenance-back>← Torna alla lista</button>
    <header class="maintenance-detail-header">
      <div>
        <p class="eyebrow">Manutenzione</p>
        <h3>${escapeHtml(item.maintenance_number)}</h3>
        <p>${escapeHtml(item.plate || item.external_identifier)}</p>
      </div>
      <span class="maintenance-status status-${escapeHtml(item.status)}">${escapeHtml(STATUS[item.status])}</span>
    </header>
    <div class="maintenance-detail-grid">
      <section><h4>Intervento</h4><dl>
        <div><dt>Mezzo</dt><dd>${escapeHtml(item.vehicle_model || "Non indicato")}</dd></div>
        <div><dt>Targa</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div>
        <div><dt>Tipologia</dt><dd>${escapeHtml(TYPE[item.maintenance_type])}</dd></div>
        <div><dt>Priorità</dt><dd>${escapeHtml(PRIORITY[item.priority])}</dd></div>
        <div><dt>Officina</dt><dd>${escapeHtml(item.repair_shop || "Da assegnare")}</dd></div>
        <div><dt>Pratica origine</dt><dd>${escapeHtml(item.damage_case_number || "Decisione Fleet")}</dd></div>
        <div><dt>Data apertura</dt><dd>${escapeHtml(date(item.opened_at))}</dd></div>
        <div><dt>Data prevista</dt><dd>${escapeHtml(date(item.expected_at))}</dd></div>
      </dl></section>
      <section><h4>Descrizione</h4><p>${escapeHtml(item.description)}</p><h4>Note</h4><p>${escapeHtml(item.notes || "Nessuna nota")}</p></section>
      <section><h4>Profilo contrattuale del mezzo</h4>${contractContext(item.asset_profile)}</section>
      <section class="maintenance-update-section"><h4>Avanzamento</h4>
        <form id="maintenanceUpdateForm" class="maintenance-form">
          <label>Stato<select name="status">${Object.entries(STATUS).map(([key, label]) => `<option value="${key}" ${key === item.status ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label>Priorità<select name="priority">${Object.entries(PRIORITY).map(([key, label]) => `<option value="${key}" ${key === item.priority ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label>Officina<input name="repair_shop" value="${escapeHtml(item.repair_shop || "")}"></label>
          <label>Data prevista<input name="expected_at" type="datetime-local" value="${item.expected_at ? escapeHtml(item.expected_at.slice(0, 16)) : ""}"></label>
          <label class="maintenance-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || "")}</textarea></label>
          <button type="submit">Aggiorna manutenzione</button>
          <p id="maintenanceActionStatus" class="section-note" role="status"></p>
        </form>
      </section>
      <section><h4>Timeline</h4><ol class="maintenance-timeline">${timeline(item.events)}</ol></section>
    </div>`;
  workspace.querySelector("[data-maintenance-back]").addEventListener("click", () => {
    workspace.classList.remove("maintenance-detail-mode");
    workspace.querySelector("#maintenanceNavigator").classList.remove("detail-open");
    selectedId = null;
    renderList();
  });
  workspace.querySelector("#maintenanceUpdateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (!values.expected_at) values.expected_at = null;
    try {
      await updateMaintenance(item.id, values);
      await refresh(item.id);
    } catch (error) {
      workspace.querySelector("#maintenanceActionStatus").textContent = error.message;
    }
  });
}

async function refresh(maintenanceId = selectedId) {
  const response = await listMaintenances();
  records = response.items;
  renderSummary(response.summary);
  renderList();
  if (maintenanceId && records.some((item) => Number(item.id) === Number(maintenanceId))) {
    await renderDetail(maintenanceId);
  }
}

function shell() {
  return `
    <header class="maintenance-header">
      <div><p class="eyebrow">Fleet Operations</p><h2 id="maintenanceWorkspaceTitle">Manutenzioni</h2><p>Gestione interventi del parco mezzi</p></div>
      <button type="button" data-new-maintenance>Nuova manutenzione</button>
    </header>
    <div class="maintenance-kpis" aria-label="Riepilogo manutenzioni">
      <article><span>Manutenzioni aperte</span><strong id="maintenanceOpen">0</strong></article>
      <article><span>Mezzi in officina</span><strong id="maintenanceWorkshop">0</strong></article>
      <article><span>Manutenzioni programmate</span><strong id="maintenanceScheduled">0</strong></article>
      <article><span>Manutenzioni concluse</span><strong id="maintenanceCompleted">0</strong></article>
    </div>
    <div id="maintenanceNavigator" class="maintenance-navigator">
      <aside class="maintenance-list-pane" aria-label="Lista manutenzioni">
        <h3>Interventi</h3><div id="maintenanceList" class="maintenance-list"></div>
      </aside>
      <div id="maintenanceDetail" class="maintenance-detail-pane">
        <div class="maintenance-empty"><strong>Seleziona una manutenzione</strong><p>Apri un intervento per seguirne stato e dettagli.</p></div>
      </div>
    </div>
    <dialog id="maintenanceEditor" class="assignment-editor fleet-dialog">
      <form id="maintenanceCreateForm">
        <div class="editor-heading">
          <div><p class="eyebrow">Fleet Operations</p><h3>Nuova manutenzione</h3></div>
          <button type="button" class="icon-button" data-close-maintenance aria-label="Chiudi">&times;</button>
        </div>
        <label>Mezzo<select name="vehicle_id" required></select></label>
        <label>Tipologia<select name="maintenance_type">${Object.entries(TYPE).map(([key, label]) => `<option value="${key}">${label}</option>`).join("")}</select></label>
        <label>Priorità<select name="priority">${Object.entries(PRIORITY).map(([key, label]) => `<option value="${key}">${label}</option>`).join("")}</select></label>
        <label>Officina<input name="repair_shop"></label>
        <label>Data prevista<input name="expected_at" type="datetime-local"></label>
        <label>Descrizione<textarea name="description" required></textarea></label>
        <label>Note<textarea name="notes"></textarea></label>
        <p data-maintenance-create-status class="section-note" role="status"></p>
        <div class="editor-actions"><button type="button" class="secondary" data-close-maintenance>Annulla</button><button type="submit">Apri manutenzione</button></div>
      </form>
    </dialog>`;
}

export async function showMaintenanceWorkspace({ maintenanceId = null } = {}) {
  const workspace = root();
  document.getElementById("damageWorkspace").hidden = true;
  document.getElementById("fleetWorkspaceHome").hidden = true;
  document.getElementById("fleetVehicleDossier").hidden = true;
  workspace.hidden = false;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    workspace.querySelector("#maintenanceList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-maintenance-id]");
      if (target) renderDetail(Number(target.dataset.maintenanceId));
    });
    workspace.querySelector("[data-new-maintenance]").addEventListener("click", async () => {
      const assets = await listFleetAssets();
      const select = workspace.querySelector("#maintenanceCreateForm [name='vehicle_id']");
      select.innerHTML = assets.items.map((asset) => `
        <option value="${asset.id}">${escapeHtml(asset.plate || asset.external_identifier)}</option>
      `).join("");
      workspace.querySelector("#maintenanceCreateForm").reset();
      workspace.querySelector("#maintenanceEditor").showModal();
    });
    workspace.querySelectorAll("[data-close-maintenance]").forEach((button) => {
      button.addEventListener("click", () => workspace.querySelector("#maintenanceEditor").close());
    });
    workspace.querySelector("#maintenanceCreateForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      values.vehicle_id = Number(values.vehicle_id);
      values.status = values.expected_at ? "programmata" : "aperta";
      if (!values.expected_at) values.expected_at = null;
      values.repair_shop ||= null;
      values.notes ||= null;
      try {
        const created = await createMaintenance(values);
        workspace.querySelector("#maintenanceEditor").close();
        await refresh(created.id);
      } catch (error) {
        workspace.querySelector("[data-maintenance-create-status]").textContent =
          error.message;
      }
    });
  }
  await refresh(maintenanceId);
}

document.addEventListener("maintenance:create-from-damage", async (event) => {
  const damage = event.detail;
  try {
    const created = await createMaintenance({
      damage_case_id: damage.id,
      description: damage.description,
      maintenance_type: damage.severity === "bassa" ? "altro" : "carrozzeria",
      priority: damage.severity || "media",
      repair_shop: damage.repair_shop || null,
      status: damage.repair_shop ? "programmata" : "aperta",
      notes: `Generata dalla pratica ${damage.case_number}`,
    });
    document.dispatchEvent(new CustomEvent("maintenance:open", {
      detail: { maintenanceId: created.id },
    }));
  } catch (error) {
    document.dispatchEvent(new CustomEvent("maintenance:error", {
      detail: { message: error.message },
    }));
  }
});

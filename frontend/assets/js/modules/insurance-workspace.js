import {
  createInsurancePolicy,
  getInsurancePolicy,
  listFleetAssets,
  listInsurancePolicies,
  updateInsurancePolicy,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";

const COVERAGE = {
  rca: "RCA",
  kasko: "Kasko",
  furto_incendio: "Furto e Incendio",
  cristalli: "Cristalli",
  eventi_atmosferici: "Eventi atmosferici",
  assistenza: "Assistenza",
  altro: "Altro",
};
const STATUS = {
  attiva: "Attiva",
  in_scadenza: "In scadenza",
  scaduta: "Scaduta",
  sospesa: "Sospesa",
};
let policies = [];
let assets = [];
let selectedId = null;
let vehicleFilter = null;

const root = () => document.getElementById("insuranceWorkspace");
const date = (value) => value
  ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("it-IT")
  : "Non indicata";
const money = (value) => value == null
  ? "Non indicato"
  : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(value));

function renderSummary(summary) {
  for (const [key, value] of Object.entries(summary)) {
    const target = root().querySelector(`[data-insurance-kpi="${key}"]`);
    if (target) target.textContent = value;
  }
}

function renderList() {
  root().querySelector("#insuranceList").innerHTML = policies.length
    ? policies.map((item) => `
      <button type="button" class="insurance-card${Number(item.id) === Number(selectedId) ? " selected" : ""}"
        data-insurance-id="${item.id}" aria-current="${Number(item.id) === Number(selectedId)}">
        <span><strong>${escapeHtml(item.plate || item.external_identifier)}</strong><small>${escapeHtml(item.vehicle_model || "Mezzo")}</small></span>
        <span><small>Compagnia</small><strong>${escapeHtml(item.company)}</strong></span>
        <span><small>Numero polizza</small>${escapeHtml(item.policy_number)}</span>
        <span><small>Copertura</small>${escapeHtml(COVERAGE[item.coverage_type])}</span>
        <span><small>Scadenza</small>${escapeHtml(date(item.expires_on))}</span>
        <span class="insurance-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span>
      </button>`).join("")
    : `<div class="insurance-empty">${
      vehicleFilter ? "Nessuna polizza per il mezzo selezionato." : "Nessuna polizza registrata."
    }</div>`;
}

function fields(item = {}) {
  return `
    <label>Mezzo<select name="vehicle_id" required ${item.id ? "disabled" : ""}>${assets.map((asset) =>
      `<option value="${asset.id}" ${Number(item.vehicle_id || vehicleFilter) === Number(asset.id) ? "selected" : ""}>${escapeHtml(asset.plate || asset.external_identifier)} · ${escapeHtml(asset.category || "Modello non indicato")} · #${asset.id}</option>`
    ).join("")}</select></label>
    <label>Compagnia assicurativa<input name="company" required value="${escapeHtml(item.company || "")}"></label>
    <label>Numero polizza<input name="policy_number" required value="${escapeHtml(item.policy_number || "")}"></label>
    <label>Tipo copertura<select name="coverage_type">${Object.entries(COVERAGE).map(([key, label]) =>
      `<option value="${key}" ${key === item.coverage_type ? "selected" : ""}>${label}</option>`
    ).join("")}</select></label>
    <label>Data decorrenza<input name="starts_on" type="date" required value="${escapeHtml(item.starts_on || "")}"></label>
    <label>Data scadenza<input name="expires_on" type="date" required value="${escapeHtml(item.expires_on || "")}"></label>
    <label>Massimale<input name="coverage_limit" type="number" min="0" step="0.01" value="${escapeHtml(item.coverage_limit || "")}"></label>
    <label>Franchigia assicurativa<input name="insurance_deductible" type="number" min="0" step="0.01" value="${escapeHtml(item.insurance_deductible || "")}"></label>
    <label>Stato<select name="status">${Object.entries(STATUS).map(([key, label]) =>
      `<option value="${key}" ${key === (item.status || "attiva") ? "selected" : ""}>${label}</option>`
    ).join("")}</select></label>
    <label class="insurance-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || "")}</textarea></label>`;
}

function openEditor(item = {}) {
  const dialog = root().querySelector("#insuranceEditor");
  dialog.querySelector("h3").textContent = item.id ? "Modifica polizza" : "Nuova polizza";
  dialog.querySelector("form").dataset.policyId = item.id || "";
  dialog.querySelector("[data-insurance-fields]").innerHTML = fields(item);
  dialog.querySelector("[data-insurance-form-status]").textContent = "";
  dialog.showModal();
}

async function renderDetail(policyId) {
  const item = await getInsurancePolicy(policyId);
  selectedId = Number(policyId);
  renderList();
  const workspace = root();
  workspace.classList.add("insurance-detail-mode");
  workspace.querySelector("#insuranceNavigator").classList.add("detail-open");
  workspace.querySelector("#insuranceDetail").innerHTML = `
    <button type="button" class="quiet insurance-mobile-back" data-insurance-back>← Torna alla lista</button>
    <header class="insurance-detail-header">
      <div><p class="eyebrow">${escapeHtml(COVERAGE[item.coverage_type])}</p>
      <h3>${escapeHtml(item.company)}</h3><p>${escapeHtml(item.plate || item.external_identifier)} · ${escapeHtml(item.policy_number)}</p></div>
      <span class="insurance-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span>
    </header>
    <dl class="insurance-detail-grid">
      <div><dt>Mezzo</dt><dd>${escapeHtml(item.vehicle_model || "Non indicato")}</dd></div>
      <div><dt>Targa</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div>
      <div><dt>Compagnia</dt><dd>${escapeHtml(item.company)}</dd></div>
      <div><dt>Numero polizza</dt><dd>${escapeHtml(item.policy_number)}</dd></div>
      <div><dt>Copertura</dt><dd>${escapeHtml(COVERAGE[item.coverage_type])}</dd></div>
      <div><dt>Decorrenza</dt><dd>${escapeHtml(date(item.starts_on))}</dd></div>
      <div><dt>Scadenza</dt><dd>${escapeHtml(date(item.expires_on))}</dd></div>
      <div><dt>Massimale</dt><dd>${escapeHtml(money(item.coverage_limit))}</dd></div>
      <div><dt>Franchigia assicurativa</dt><dd>${escapeHtml(money(item.insurance_deductible))}</dd></div>
      <div class="insurance-detail-wide"><dt>Note</dt><dd>${escapeHtml(item.notes || "Nessuna nota")}</dd></div>
    </dl>
    <button type="button" data-edit-insurance>Modifica polizza</button>`;
  workspace.querySelector("[data-insurance-back]").addEventListener("click", () => {
    workspace.classList.remove("insurance-detail-mode");
    workspace.querySelector("#insuranceNavigator").classList.remove("detail-open");
  });
  workspace.querySelector("[data-edit-insurance]").addEventListener("click", () => openEditor(item));
}

async function refresh(policyId = selectedId) {
  const response = await listInsurancePolicies({ vehicle_id: vehicleFilter });
  policies = response.items;
  renderSummary(response.summary);
  renderList();
  if (policyId && policies.some((item) => Number(item.id) === Number(policyId))) {
    await renderDetail(policyId);
  }
}

function shell() {
  return `
    <header class="insurance-header"><div><p class="eyebrow">Fleet Operations</p>
      <h2 id="insuranceWorkspaceTitle">Assicurazioni</h2>
      <p>Gestione delle coperture assicurative del parco mezzi</p></div>
      <button type="button" data-new-insurance>Nuova polizza</button></header>
    <div class="insurance-kpis" aria-label="Riepilogo polizze">
      <article><span>Polizze</span><strong data-insurance-kpi="total">0</strong></article>
      <article><span>Attive</span><strong data-insurance-kpi="active">0</strong></article>
      <article><span>In scadenza</span><strong data-insurance-kpi="expiring">0</strong></article>
      <article><span>Scadute</span><strong data-insurance-kpi="expired">0</strong></article>
      <article><span>Sospese</span><strong data-insurance-kpi="suspended">0</strong></article>
    </div>
    <div id="insuranceNavigator" class="insurance-navigator">
      <aside class="insurance-list-pane" aria-label="Lista polizze"><div id="insuranceList" class="insurance-list"></div></aside>
      <div id="insuranceDetail" class="insurance-detail-pane"><div class="insurance-empty">
        <strong>Seleziona una polizza</strong><p>Apri una polizza per consultarne copertura e scadenza.</p>
      </div></div>
    </div>
    <dialog id="insuranceEditor" class="assignment-editor fleet-dialog"><form>
      <div class="editor-heading"><div><p class="eyebrow">Copertura mezzo</p><h3>Nuova polizza</h3></div>
      <button type="button" class="icon-button" data-close-insurance aria-label="Chiudi">&times;</button></div>
      <div class="insurance-form" data-insurance-fields></div>
      <p data-insurance-form-status role="status"></p>
      <div class="editor-actions"><button type="button" class="secondary" data-close-insurance>Annulla</button><button type="submit">Salva polizza</button></div>
    </form></dialog>`;
}

export async function showInsuranceWorkspace({ policyId = null, vehicleId = null } = {}) {
  const workspace = root();
  ["damageWorkspace", "maintenanceWorkspace", "documentsWorkspace",
    "franchiseWorkspace", "fleetWorkspaceHome", "fleetVehicleDossier"].forEach((id) => {
    document.getElementById(id).hidden = true;
  });
  workspace.hidden = false;
  vehicleFilter = vehicleId ? Number(vehicleId) : null;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    workspace.querySelector("#insuranceList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-insurance-id]");
      if (target) renderDetail(Number(target.dataset.insuranceId));
    });
    workspace.querySelector("[data-new-insurance]").addEventListener("click", () => openEditor());
    workspace.querySelectorAll("[data-close-insurance]").forEach((button) => {
      button.addEventListener("click", () => workspace.querySelector("#insuranceEditor").close());
    });
    workspace.querySelector("#insuranceEditor form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = Number(event.currentTarget.dataset.policyId || 0);
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      for (const field of ["coverage_limit", "insurance_deductible", "notes"]) values[field] ||= null;
      if (id) delete values.vehicle_id;
      else values.vehicle_id = Number(values.vehicle_id);
      try {
        const saved = id
          ? await updateInsurancePolicy(id, values)
          : await createInsurancePolicy(values);
        workspace.querySelector("#insuranceEditor").close();
        await refresh(saved.id);
      } catch (error) {
        workspace.querySelector("[data-insurance-form-status]").textContent = error.message;
      }
    });
  }
  assets = (await listFleetAssets()).items;
  await refresh(policyId);
}

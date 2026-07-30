import {
  getFranchiseCase,
  listFranchiseCases,
  updateFranchiseCase,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";

const STATUS = {
  da_valutare: "Da valutare",
  in_verifica: "In verifica",
  applicata: "Applicata",
  non_applicabile: "Non applicabile",
  chiusa: "Chiusa",
};
const CONTRACT = {
  lungo_termine: "Lungo termine",
  breve_termine: "Breve termine",
  proprieta: "Proprietà",
  leasing: "Leasing",
  altro: "Altro",
};
let records = [];
let selectedId = null;
let vehicleFilter = null;

const root = () => document.getElementById("franchiseWorkspace");
const money = (value) => value == null
  ? "Non prevista"
  : new Intl.NumberFormat("it-IT", {
    style: "currency", currency: "EUR",
  }).format(Number(value));

function renderSummary(summary) {
  for (const [key, value] of Object.entries(summary)) {
    const target = root().querySelector(`[data-franchise-kpi="${key}"]`);
    if (target) target.textContent = value;
  }
}

function renderList() {
  root().querySelector("#franchiseList").innerHTML = records.length
    ? records.map((item) => `
      <button type="button" class="franchise-card${Number(item.id) === Number(selectedId) ? " selected" : ""}"
        data-franchise-id="${item.id}" aria-current="${Number(item.id) === Number(selectedId)}">
        <span><strong>${escapeHtml(item.plate || item.external_identifier)}</strong><small>${escapeHtml(item.vehicle_model || "Mezzo")}</small></span>
        <span><small>Contratto</small><strong>${escapeHtml(CONTRACT[item.contract_type] || "Non configurato")}</strong></span>
        <span><small>Pratica danno</small>${escapeHtml(item.damage_case_number)}</span>
        <span><small>Manutenzione</small>${escapeHtml(item.maintenance_number || "Non collegata")}</span>
        <span><small>Franchigia prevista</small><strong>${escapeHtml(money(item.franchise_expected))}</strong></span>
        <span class="franchise-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span>
      </button>`).join("")
    : `<div class="franchise-empty">${
      vehicleFilter
        ? "Nessuna franchigia per il mezzo selezionato."
        : "Nessuna valutazione franchigia registrata."
    }</div>`;
}

async function renderDetail(caseId) {
  const item = await getFranchiseCase(caseId);
  selectedId = Number(caseId);
  renderList();
  const workspace = root();
  workspace.classList.add("franchise-detail-mode");
  workspace.querySelector("#franchiseNavigator").classList.add("detail-open");
  workspace.querySelector("#franchiseDetail").innerHTML = `
    <button type="button" class="quiet franchise-mobile-back" data-franchise-back>← Torna alla lista</button>
    <header class="franchise-detail-header">
      <div><p class="eyebrow">Valutazione franchigia</p><h3>${escapeHtml(item.damage_case_number)}</h3>
      <p>${escapeHtml(item.plate || item.external_identifier)} · ${escapeHtml(item.vehicle_model || "Mezzo")}</p></div>
      <span class="franchise-status status-${item.status}">${escapeHtml(STATUS[item.status])}</span>
    </header>
    <dl class="franchise-detail-grid">
      <div><dt>Mezzo</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div>
      <div><dt>Tipo contratto</dt><dd>${escapeHtml(CONTRACT[item.contract_type] || "Non configurato")}</dd></div>
      <div><dt>Società</dt><dd>${escapeHtml(item.contract_company || "Non registrata")}</dd></div>
      <div><dt>Contratto</dt><dd>${escapeHtml(item.contract_number || "Non registrato")}</dd></div>
      <div class="franchise-value"><dt>Franchigia prevista</dt><dd>${escapeHtml(money(item.franchise_expected))}</dd></div>
      <div><dt>Pratica danno</dt><dd>${escapeHtml(item.damage_case_number)}</dd></div>
      <div><dt>Manutenzione</dt><dd>${escapeHtml(item.maintenance_number || "Non collegata")}</dd></div>
      <div class="franchise-detail-wide"><dt>Motivazione</dt><dd>${escapeHtml(item.motivation || "Da definire")}</dd></div>
      <div class="franchise-detail-wide"><dt>Note</dt><dd>${escapeHtml(item.notes || "Nessuna nota")}</dd></div>
    </dl>
    <section class="franchise-assessment"><h4>Aggiorna valutazione</h4>
      <form id="franchiseUpdateForm" class="franchise-form">
        <label>Stato<select name="status">${Object.entries(STATUS).map(([key, label]) =>
          `<option value="${key}" ${key === item.status ? "selected" : ""}>${label}</option>`
        ).join("")}</select></label>
        <label>Motivazione<textarea name="motivation">${escapeHtml(item.motivation || "")}</textarea></label>
        <label class="franchise-form-wide">Note<textarea name="notes">${escapeHtml(item.notes || "")}</textarea></label>
        <button type="submit">Salva valutazione</button><p data-franchise-status role="status"></p>
      </form>
      <p class="section-note">L’importo è letto in tempo reale dal Fleet Asset Profile e non viene copiato nella valutazione.</p>
    </section>`;
  workspace.querySelector("[data-franchise-back]").addEventListener("click", () => {
    workspace.classList.remove("franchise-detail-mode");
    workspace.querySelector("#franchiseNavigator").classList.remove("detail-open");
  });
  workspace.querySelector("#franchiseUpdateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    values.motivation ||= null;
    values.notes ||= null;
    try {
      await updateFranchiseCase(item.id, values);
      await refresh(item.id);
    } catch (error) {
      workspace.querySelector("[data-franchise-status]").textContent = error.message;
    }
  });
}

async function refresh(caseId = selectedId) {
  const response = await listFranchiseCases({ vehicle_id: vehicleFilter });
  records = response.items;
  renderSummary(response.summary);
  renderList();
  if (caseId && records.some((item) => Number(item.id) === Number(caseId))) {
    await renderDetail(caseId);
  }
}

function shell() {
  return `
    <header class="franchise-header"><div><p class="eyebrow">Fleet Operations</p>
      <h2 id="franchiseWorkspaceTitle">Franchigie</h2>
      <p>Gestione delle franchigie contrattuali dei mezzi</p></div></header>
    <div class="franchise-kpis" aria-label="Riepilogo franchigie">
      <article><span>Valutazioni</span><strong data-franchise-kpi="total">0</strong></article>
      <article><span>Da valutare</span><strong data-franchise-kpi="to_evaluate">0</strong></article>
      <article><span>In verifica</span><strong data-franchise-kpi="in_review">0</strong></article>
      <article><span>Applicate</span><strong data-franchise-kpi="applied">0</strong></article>
      <article><span>Chiuse</span><strong data-franchise-kpi="closed">0</strong></article>
    </div>
    <div id="franchiseNavigator" class="franchise-navigator">
      <aside class="franchise-list-pane" aria-label="Lista pratiche con franchigia">
        <div id="franchiseList" class="franchise-list"></div>
      </aside>
      <div id="franchiseDetail" class="franchise-detail-pane">
        <div class="franchise-empty"><strong>Seleziona una valutazione</strong>
        <p>Apri una pratica per verificare contratto e franchigia prevista.</p></div>
      </div>
    </div>`;
}

export async function showFranchiseWorkspace({ franchiseId = null, vehicleId = null } = {}) {
  const workspace = root();
  ["damageWorkspace", "maintenanceWorkspace", "documentsWorkspace",
    "fleetWorkspaceHome", "fleetVehicleDossier"].forEach((id) => {
    document.getElementById(id).hidden = true;
  });
  workspace.hidden = false;
  vehicleFilter = vehicleId ? Number(vehicleId) : null;
  if (!workspace.dataset.ready) {
    workspace.innerHTML = shell();
    workspace.dataset.ready = "true";
    workspace.querySelector("#franchiseList").addEventListener("click", (event) => {
      const target = event.target.closest("[data-franchise-id]");
      if (target) renderDetail(Number(target.dataset.franchiseId));
    });
  }
  await refresh(franchiseId);
}

import { getFleetVision } from "../api.js";
import { escapeHtml } from "../utils/dom.js";

let state = { items: [], selected: null };
const root = () => document.getElementById("fleetVisionWorkspace");
const statusLabel = (value) => ({
  disponibile: "Disponibile", disponibile_con_limitazioni: "Disponibile con limitazioni",
  indisponibile: "Indisponibile", in_manutenzione: "In manutenzione",
  in_officina: "In officina", available: "Disponibile", reserve: "Disponibile con limitazioni",
  unavailable: "Indisponibile", maintenance: "In manutenzione", workshop: "In officina",
}[value] || "Non classificato");
const contractLabel = (value) => ({
  lungo_termine: "Lungo termine", breve_termine: "Breve termine",
  proprieta: "Proprietà", leasing: "Leasing", altro: "Altro",
}[value] || "Non registrato");

function listItem(item) {
  return `<button type="button" class="fve-vehicle ${state.selected?.id === item.id ? "active" : ""}" data-fve-vehicle="${item.id}">
    <strong>${escapeHtml(item.plate || item.external_identifier)}</strong>
    <span>${escapeHtml(item.vehicle_model || "Modello non registrato")}</span>
    <small>${escapeHtml(statusLabel(item.operational_status))}</small>
  </button>`;
}

function metric(label, value, action, actionLabel) {
  return `<article><span>${escapeHtml(label)}</span><strong>${value ?? "Non determinabile"}</strong>
    ${action ? `<button type="button" class="quiet" data-fve-action="${action}">${escapeHtml(actionLabel)}</button>` : ""}</article>`;
}

function detail(item) {
  if (!item) return `<div class="view-state"><strong>Seleziona un mezzo</strong><p>Apri un mezzo per consultarne il Fleet Insight.</p></div>`;
  const policy = item.insurance
    ? `${escapeHtml(item.insurance.company)} · ${escapeHtml(item.insurance.policy_number)} · ${escapeHtml(item.insurance.status)}`
    : "Non registrata";
  return `<button type="button" class="quiet fve-back" data-fve-back>← Torna alla lista</button>
    <p class="eyebrow">Fleet Insight</p><h3>${escapeHtml(item.plate || item.external_identifier)}</h3>
    <dl class="fve-identity">
      <div><dt>Stato operativo</dt><dd>${escapeHtml(statusLabel(item.operational_status))}</dd></div>
      <div><dt>Motivazione</dt><dd>${escapeHtml(item.operational_status_reason || "Non registrata")}</dd></div>
      <div><dt>Tipo contratto</dt><dd>${escapeHtml(contractLabel(item.contract_type))}</dd></div>
      <div><dt>Assicurazione</dt><dd>${policy}</dd></div>
    </dl>
    <section class="fve-indicators" aria-label="Indicatori oggettivi">
      ${metric("Danni aperti", item.damage_open, "damage", "Apri Danni")}
      ${metric("Danni chiusi", item.damage_closed)}
      ${metric("Manutenzioni aperte", item.maintenance_open, "maintenance", "Apri Manutenzioni")}
      ${metric("Manutenzioni concluse", item.maintenance_completed)}
      ${metric("Documenti mancanti", item.missing_documents, "documents", "Apri Documenti")}
      ${metric("Franchigie aperte", item.franchises_open)}
      ${metric("Noleggi attivi", item.rentals_active)}
      ${metric("Scadenze imminenti", item.deadlines_imminent)}
      ${metric("Giorni fermo", item.days_stopped)}
      ${metric("Movimentazioni Journal", item.movement_count)}
    </section>
    <div class="fve-actions"><button type="button" class="primary" data-fve-action="library">Apri dossier mezzo</button></div>`;
}

function render() {
  root().querySelector("[data-fve-list]").innerHTML = state.items.length
    ? state.items.map(listItem).join("") : `<div class="view-state">Nessun mezzo disponibile.</div>`;
  root().querySelector("[data-fve-detail]").innerHTML = detail(state.selected);
  root().classList.toggle("detail-open", Boolean(state.selected));
}

export async function showFleetVisionWorkspace(options = {}) {
  document.querySelectorAll("#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace,#deadlinesWorkspace,#journalControlRoom")
    .forEach((element) => { element.hidden = true; });
  root().hidden = false;
  root().innerHTML = `<header><p class="eyebrow">Fleet Operations</p><h2 id="fleetVisionWorkspaceTitle">Fleet Vision Engine</h2>
      <p>Vista unificata e analisi del parco mezzi</p></header>
    <section class="fve-kpis" aria-label="Riepilogo Fleet Vision">
      ${["operational","unavailable","in_maintenance","open_damages","open_maintenances","active_rentals"].map((key) => `<article><span data-fve-kpi-label="${key}"></span><strong data-fve-kpi="${key}">0</strong></article>`).join("")}
    </section>
    <div class="fve-master-detail"><aside data-fve-list aria-label="Elenco mezzi"></aside><article data-fve-detail></article></div>`;
  const response = await getFleetVision(options.vehicle_id ? { vehicle_id: options.vehicle_id } : {});
  const labels = { operational: "Mezzi operativi", unavailable: "Mezzi indisponibili", in_maintenance: "Mezzi in manutenzione", open_damages: "Danni aperti", open_maintenances: "Manutenzioni aperte", active_rentals: "Noleggi attivi" };
  for (const [key, value] of Object.entries(response.summary)) {
    root().querySelector(`[data-fve-kpi="${key}"]`).textContent = value;
    root().querySelector(`[data-fve-kpi-label="${key}"]`).textContent = labels[key];
  }
  state = { items: response.items, selected: response.items[0] || null };
  render();
}

document.addEventListener("click", (event) => {
  const vehicle = event.target.closest("[data-fve-vehicle]");
  if (vehicle) { state.selected = state.items.find((item) => item.id === Number(vehicle.dataset.fveVehicle)); render(); }
  if (event.target.closest("[data-fve-back]")) root().classList.remove("detail-open");
  const action = event.target.closest("[data-fve-action]")?.dataset.fveAction;
  if (!action || !state.selected) return;
  root().hidden = true;
  if (action === "library") document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: state.selected.id } }));
  if (action === "damage") document.dispatchEvent(new CustomEvent("damage:open", { detail: { vehicle_id: state.selected.id } }));
  if (action === "maintenance") document.dispatchEvent(new CustomEvent("maintenance:open", { detail: { vehicle_id: state.selected.id } }));
  if (action === "documents") document.dispatchEvent(new CustomEvent("documents:open", { detail: { vehicle_id: state.selected.id } }));
});

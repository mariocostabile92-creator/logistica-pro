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
  const insights = item.insights.map((insight) => `<article>
    <span>${escapeHtml(insight.label)}</span><strong>${escapeHtml(insight.value ?? "Non disponibile")}</strong>
    <small>Fonte: ${escapeHtml(insight.source)}</small>
    <button type="button" class="quiet" data-fve-action="${escapeHtml(insight.module)}">Apri modulo origine</button>
  </article>`).join("");
  const timeline = item.timeline.length
    ? item.timeline.map((entry) => `<li><time>${escapeHtml(new Date(entry.occurred_at).toLocaleString("it-IT"))}</time>
        <strong>${escapeHtml(entry.label)}</strong><small>Fonte: ${escapeHtml(entry.module)}</small>
        <button type="button" class="quiet" data-fve-action="${escapeHtml(entry.module)}">Apri modulo origine</button></li>`).join("")
    : `<li class="view-state">Nessun evento operativo disponibile.</li>`;
  const decisions = item.decisions?.length
    ? item.decisions.map((decision) => `<article class="fde-decision priority-${escapeHtml(decision.priority)}">
        <header><span class="fde-priority">${escapeHtml(decision.priority)}</span><h5>${escapeHtml(decision.title)}</h5></header>
        <p>${escapeHtml(decision.description)}</p>
        <dl>
          <div><dt>Origine</dt><dd>${escapeHtml(decision.origin)}</dd></div>
          <div><dt>Modulo</dt><dd>${escapeHtml(decision.module)}</dd></div>
          <div><dt>Perché</dt><dd>${escapeHtml(decision.why)}</dd></div>
        </dl>
        <button type="button" class="quiet" data-fve-action="${escapeHtml(decision.module)}">Apri</button>
      </article>`).join("")
    : `<div class="view-state"><strong>Nessuna attenzione operativa</strong><p>Le regole non rilevano condizioni da evidenziare per questo mezzo.</p></div>`;
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
    <section class="fve-correlation"><h4>Insight correlati</h4><div class="fve-insights">${insights}</div></section>
    <section class="fde-center" aria-labelledby="fdeDecisionCenterTitle">
      <h4 id="fdeDecisionCenterTitle">Decision Center</h4>
      <p>Attenzioni generate da regole operative verificabili.</p>
      <div class="fde-decisions">${decisions}</div>
    </section>
    <section class="fve-timeline"><h4>Cronologia unificata</h4><ol>${timeline}</ol></section>
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
    <section class="fve-health" aria-labelledby="fleetHealthTitle"><h3 id="fleetHealthTitle">Fleet Health</h3>
      <div>${["open_damages","open_maintenances","active_rentals","missing_documents","expired_insurance","expiring_contracts"].map((key) => `<article><span data-fve-health-label="${key}"></span><strong data-fve-health="${key}">0</strong></article>`).join("")}</div>
    </section>
    <div class="fve-master-detail"><aside data-fve-list aria-label="Elenco mezzi"></aside><article data-fve-detail></article></div>`;
  const response = await getFleetVision(options.vehicle_id ? { vehicle_id: options.vehicle_id } : {});
  const labels = { operational: "Mezzi operativi", unavailable: "Mezzi indisponibili", in_maintenance: "Mezzi in manutenzione", open_damages: "Danni aperti", open_maintenances: "Manutenzioni aperte", active_rentals: "Noleggi attivi", missing_documents: "Documenti mancanti", expired_insurance: "Assicurazioni scadute", expiring_contracts: "Contratti in scadenza" };
  for (const [key, value] of Object.entries(response.summary)) {
    const kpi = root().querySelector(`[data-fve-kpi="${key}"]`);
    if (kpi) {
      kpi.textContent = value;
      root().querySelector(`[data-fve-kpi-label="${key}"]`).textContent = labels[key];
    }
    const health = root().querySelector(`[data-fve-health="${key}"]`);
    if (health) {
      health.textContent = value;
      root().querySelector(`[data-fve-health-label="${key}"]`).textContent = labels[key];
    }
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
  if (action === "journal") document.querySelector("[data-fleet-module='journal']")?.click();
  if (action === "insurance") document.dispatchEvent(new CustomEvent("insurance:open", { detail: { vehicle_id: state.selected.id } }));
  if (action === "rentals") document.dispatchEvent(new CustomEvent("rental:open", { detail: { vehicle_id: state.selected.id } }));
  if (action === "franchises") document.dispatchEvent(new CustomEvent("franchise:open", { detail: { vehicle_id: state.selected.id } }));
  if (action === "deadlines") document.querySelector("[data-fleet-module='deadlines']")?.click();
});

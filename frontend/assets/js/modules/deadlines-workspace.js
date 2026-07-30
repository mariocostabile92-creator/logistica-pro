import { listFleetDeadlines } from "../api.js";
import { escapeHtml } from "../utils/dom.js";

const LABELS = {
  revisione: "Revisione", assicurazione: "Assicurazione", bollo: "Bollo",
  contratto: "Contratto", manutenzione_programmata: "Manutenzione programmata",
  altro: "Altro",
};
let state = { items: [], filtered: [], selected: null, filter: "all", search: "" };
const root = () => document.getElementById("deadlinesWorkspace");
const dateLabel = (value) => new Date(`${value}T00:00:00`).toLocaleDateString("it-IT");
const typeLabel = (value) => LABELS[value] || value.replaceAll("_", " ");

function matches(item) {
  const sourceFilters = { documents: "document", insurance: "insurance", contracts: "contract", maintenance: "maintenance" };
  const filterMatch = state.filter === "all"
    || item.status_bucket === state.filter
    || (state.filter === "thirty_days" && item.days_remaining >= 0 && item.days_remaining <= 30)
    || item.source_module === sourceFilters[state.filter];
  const haystack = [item.plate, item.external_identifier, item.deadline_type, item.module_label, item.company]
    .filter(Boolean).join(" ").toLocaleLowerCase("it");
  return filterMatch && haystack.includes(state.search.toLocaleLowerCase("it"));
}

function render() {
  state.filtered = state.items.filter(matches);
  if (!state.filtered.some((item) => item.id === state.selected?.id)) state.selected = state.filtered[0] || null;
  root().querySelector("[data-deadline-list]").innerHTML = state.filtered.length
    ? state.filtered.map((item) => `<button type="button" class="deadline-item ${item.id === state.selected?.id ? "active" : ""}" data-deadline-id="${escapeHtml(item.id)}">
        <strong>${escapeHtml(item.plate || item.external_identifier)}</strong><span>${escapeHtml(typeLabel(item.deadline_type))}</span>
        <small>${escapeHtml(item.module_label)} · ${escapeHtml(dateLabel(item.due_date))}</small>
        <em class="deadline-status ${item.status_bucket}">${escapeHtml(item.status)}</em>
      </button>`).join("")
    : `<div class="view-state">Nessuna scadenza corrisponde ai criteri.</div>`;
  const item = state.selected;
  root().querySelector("[data-deadline-detail]").innerHTML = item ? `
    <button type="button" class="quiet deadline-back" data-deadline-back>← Torna alla lista</button>
    <p class="eyebrow">${escapeHtml(item.module_label)}</p>
    <h3>${escapeHtml(typeLabel(item.deadline_type))}</h3>
    <dl class="deadline-detail-grid">
      <div><dt>Mezzo</dt><dd>${escapeHtml(item.vehicle_model || "Non indicato")}</dd></div>
      <div><dt>Targa</dt><dd>${escapeHtml(item.plate || item.external_identifier)}</dd></div>
      <div><dt>Data</dt><dd>${escapeHtml(dateLabel(item.due_date))}</dd></div>
      <div><dt>Stato</dt><dd>${escapeHtml(item.status)}</dd></div>
      <div><dt>Modulo origine</dt><dd>${escapeHtml(item.module_label)}</dd></div>
      <div><dt>Società</dt><dd>${escapeHtml(item.company || "Non indicata")}</dd></div>
    </dl>
    <button type="button" class="primary" data-open-deadline-source>Apri modulo origine</button>`
    : `<div class="view-state"><strong>Seleziona una scadenza</strong><p>Apri una voce per consultarne origine e stato.</p></div>`;
  root().classList.toggle("detail-open", Boolean(item));
}

export async function showDeadlinesWorkspace(options = {}) {
  document.querySelectorAll("#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace")
    .forEach((element) => { element.hidden = true; });
  root().hidden = false;
  root().innerHTML = `
    <header class="deadline-header"><div><p class="eyebrow">Fleet Operations</p><h2 id="deadlinesWorkspaceTitle">Scadenziario</h2>
      <p>Controllo centralizzato delle scadenze del parco mezzi</p></div></header>
    <section class="deadline-kpis" aria-label="Riepilogo scadenze"></section>
    <div class="deadline-tools"><label>Cerca<input type="search" data-deadline-search placeholder="Targa, tipo, modulo o società"></label>
      <label>Filtro<select data-deadline-filter><option value="all">Tutte</option><option value="expired">Scadute</option><option value="today">Oggi</option>
      <option value="seven_days">7 giorni</option><option value="thirty_days">30 giorni</option><option value="documents">Documenti</option>
      <option value="insurance">Assicurazioni</option><option value="contracts">Contratti</option><option value="maintenance">Manutenzioni</option></select></label></div>
    <div class="deadline-master-detail"><aside data-deadline-list aria-label="Lista scadenze"></aside><article data-deadline-detail></article></div>`;
  const response = await listFleetDeadlines(options.vehicle_id ? { vehicle_id: options.vehicle_id } : {});
  state = { items: response.items, filtered: [], selected: null, filter: "all", search: "" };
  root().querySelector(".deadline-kpis").innerHTML = `
    <article><span>Scadute</span><strong>${response.summary.expired}</strong></article>
    <article><span>In scadenza</span><strong>${response.summary.expiring}</strong></article>
    <article><span>Oggi</span><strong>${response.summary.today}</strong></article>
    <article><span>Prossimi 30 giorni</span><strong>${response.summary.next_30_days}</strong></article>`;
  render();
}

document.addEventListener("input", (event) => {
  if (!event.target.matches("[data-deadline-search]")) return;
  state.search = event.target.value; render();
});
document.addEventListener("change", (event) => {
  if (!event.target.matches("[data-deadline-filter]")) return;
  state.filter = event.target.value; render();
});
document.addEventListener("click", (event) => {
  const entry = event.target.closest("[data-deadline-id]");
  if (entry) { state.selected = state.items.find((item) => item.id === entry.dataset.deadlineId); render(); }
  if (event.target.closest("[data-deadline-back]")) root().classList.remove("detail-open");
  if (event.target.closest("[data-open-deadline-source]") && state.selected) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("deadline:open-source", { detail: state.selected }));
  }
});

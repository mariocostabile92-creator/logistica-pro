import { listJournalControlRoom } from "../api.js";
import { escapeHtml } from "../utils/dom.js";
import { mountJournalSharedAccess } from "./journal-shared-access.js";

let state = { items: [], selected: null, vehicle_id: null };
const root = () => document.getElementById("journalControlRoom");
const operation = value => value === "check_out" ? "Presa in carico" : "Rientro";
const status = value => ({
  generated: "Generata",
  opened: "Aperta",
  in_progress: "In compilazione",
  completed: "Completata",
  con_anomalia: "Completata con anomalia",
}[value] || "Non classificata");
const when = value => new Date(value).toLocaleString("it-IT");

function card(item) {
  return `<button type="button" class="jcr-item ${state.selected?.id === item.id ? "active" : ""}" data-jcr-id="${escapeHtml(item.id)}">
    <strong>${escapeHtml(item.plate_snapshot)}</strong><span>${escapeHtml(operation(item.operation_type))}</span>
    <small>${escapeHtml(when(item.occurred_at))} · ${escapeHtml(item.declared_driver_identifier)} · ${escapeHtml(item.origin)}</small>
    <em class="${escapeHtml(item.status)}">${escapeHtml(status(item.status))}</em>
  </button>`;
}

function detail(item) {
  if (!item) return `<div class="view-state"><strong>Seleziona una procedura</strong><p>Apri una registrazione per consultarne i dettagli.</p></div>`;
  const equipment = item.equipment.length
    ? item.equipment.map(entry => `<li>${escapeHtml(entry.equipment_label_snapshot)}: ${escapeHtml(entry.equipment_status)}${entry.note ? ` · ${escapeHtml(entry.note)}` : ""}</li>`).join("")
    : "<li>Nessuna dotazione registrata</li>";
  const media = item.media.length
    ? item.media.map(entry => `<a href="${escapeHtml(entry.url)}" target="_blank" rel="noopener">${entry.media_type.startsWith("video") ? "Video" : "Foto"} ${entry.display_order + 1}</a>`).join("")
    : "Nessun allegato";
  const warnings = item.warnings?.length
    ? `<section class="jcr-warnings"><h4>Avvisi smart</h4><ul>${item.warnings.map(warning => `<li>${escapeHtml(warning.message)}</li>`).join("")}</ul></section>`
    : "";
  const damage = item.damage_case_id
    ? `<div class="jcr-damage"><strong>${escapeHtml(item.damage_case_number)}</strong><span>${escapeHtml(item.damage_case_status)}</span><button type="button" class="quiet" data-jcr-damage="${item.damage_case_id}">Apri pratica</button></div>`
    : item.anomaly_present ? `<div class="jcr-damage"><strong>Anomalia da gestire</strong><button type="button" class="quiet" data-jcr-damage-new>Apri Danni</button></div>` : "";
  return `<button type="button" class="quiet jcr-back" data-jcr-back>← Torna alla lista</button>
    <p class="eyebrow">${escapeHtml(status(item.status))}</p><h3>${escapeHtml(operation(item.operation_type))}</h3>
    <dl class="jcr-detail-grid">
      <div><dt>Driver</dt><dd>${escapeHtml(item.declared_driver_identifier)}</dd></div>
      <div><dt>Mezzo</dt><dd>${escapeHtml(item.plate_snapshot)} · ${escapeHtml(item.vehicle_model || "Modello non registrato")}</dd></div>
      <div><dt>Data e ora</dt><dd>${escapeHtml(when(item.occurred_at))}</dd></div>
      <div><dt>Stato</dt><dd>${escapeHtml(status(item.status))}</dd></div>
      <div><dt>Origine</dt><dd>${escapeHtml(item.origin)}</dd></div>
      <div><dt>Km</dt><dd>${item.odometer_km ?? "Non registrati"}</dd></div>
      <div><dt>Carburante</dt><dd>${item.fuel_percentage == null ? "Non registrato" : `${item.fuel_percentage}%`}</dd></div>
      <div><dt>Pulizia</dt><dd>${escapeHtml(item.cleanliness_status || "Non registrata")}</dd></div>
      <div><dt>Anomalie</dt><dd>${escapeHtml(item.anomaly_description || "Nessuna")}</dd></div>
      <div><dt>Note</dt><dd>${escapeHtml(item.operational_note || "Nessuna")}</dd></div>
      <div><dt>ID documento operativo</dt><dd>${escapeHtml(item.operational_document_id || "Non disponibile")}</dd></div>
    </dl>
    ${warnings}<section><h4>Checklist e dotazioni</h4><ul>${equipment}</ul></section>
    <section><h4>Foto e video</h4><div class="jcr-media">${media}</div></section>${damage}
    <div class="jcr-actions">
      ${item.receipt_url ? `<a class="header-config-button" href="${escapeHtml(item.receipt_url)}" target="_blank" rel="noopener">Apri documento operativo</a>` : ""}
      <button type="button" class="secondary" data-jcr-vehicle="${item.asset_id}">Apri dossier mezzo</button>
    </div>`;
}

async function load(preferredId = state.selected?.id) {
  const params = { vehicle_id: state.vehicle_id };
  for (const [selector, key] of [["[data-jcr-search]", "search"], ["[data-jcr-operation]", "operation_type"], ["[data-jcr-anomaly]", "anomaly"], ["[data-jcr-period]", "period"]]) {
    const value = root().querySelector(selector)?.value;
    if (value) params[key] = value;
  }
  const response = await listJournalControlRoom(params);
  state.items = response.items;
  state.selected = state.items.find(item => item.id === preferredId) || state.items[0] || null;
  root().querySelector("[data-jcr-list]").innerHTML = state.items.length
    ? state.items.map(card).join("")
    : `<div class="view-state">Nessuna procedura trovata.</div>`;
  root().querySelector("[data-jcr-detail]").innerHTML = detail(state.selected);
  root().classList.toggle("detail-open", Boolean(state.selected));
  for (const [key, value] of Object.entries(response.summary)) {
    root().querySelector(`[data-jcr-kpi="${key}"]`).textContent = value;
  }
}

export async function showJournalControlRoom(options = {}) {
  document.querySelectorAll("#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace,#deadlinesWorkspace")
    .forEach(element => { element.hidden = true; });
  state = { items: [], selected: null, vehicle_id: options.vehicle_id || null };
  root().hidden = false;
  root().innerHTML = `<header class="jcr-header"><div><p class="eyebrow">Fleet Operations</p><h2 id="journalControlRoomTitle">Journal Control Room</h2><p>Controllo delle procedure avviate autonomamente dai driver tramite il link condiviso</p></div></header>
    <section class="jcr-shared-access" data-jcr-shared-access aria-label="Accesso condiviso Driver Journal"></section>
    <section class="jcr-kpis" aria-label="Riepilogo procedure">
      <article><span>Completate oggi</span><strong data-jcr-kpi="completed_today">0</strong></article>
      <article><span>Prese in carico</span><strong data-jcr-kpi="check_outs">0</strong></article>
      <article><span>Rientri</span><strong data-jcr-kpi="check_ins">0</strong></article>
      <article><span>Con anomalie</span><strong data-jcr-kpi="with_anomalies">0</strong></article>
      <article><span>Incomplete</span><strong data-jcr-kpi="incomplete">0</strong></article>
    </section>
    <div class="jcr-tools"><label>Ricerca<input data-jcr-search type="search" placeholder="Driver, targa, data, note"></label>
      <label>Procedura<select data-jcr-operation><option value="">Tutte</option><option value="check_out">Prese in carico</option><option value="check_in">Rientri</option></select></label>
      <label>Anomalie<select data-jcr-anomaly><option value="">Tutte</option><option value="with">Con anomalie</option><option value="without">Senza anomalie</option></select></label>
      <label>Periodo<select data-jcr-period><option value="">Tutto</option><option value="today">Oggi</option><option value="7d">Ultimi 7 giorni</option><option value="30d">Ultimi 30 giorni</option></select></label>
    </div>
    <div class="jcr-master-detail"><aside data-jcr-list aria-label="Lista procedure"></aside><article data-jcr-detail></article></div>`;
  await mountJournalSharedAccess(root().querySelector("[data-jcr-shared-access]"));
  await load();
}

document.addEventListener("input", event => {
  if (event.target.matches("[data-jcr-search]")) load();
});
document.addEventListener("change", event => {
  if (event.target.matches("[data-jcr-operation],[data-jcr-anomaly],[data-jcr-period]")) load();
});
document.addEventListener("click", event => {
  const entry = event.target.closest("[data-jcr-id]");
  if (entry) load(entry.dataset.jcrId);
  if (event.target.closest("[data-jcr-back]")) root().classList.remove("detail-open");
  const vehicle = event.target.closest("[data-jcr-vehicle]")?.dataset.jcrVehicle;
  if (vehicle) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: Number(vehicle) } }));
  }
  const damage = event.target.closest("[data-jcr-damage]")?.dataset.jcrDamage;
  if (damage) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("damage:open", { detail: { caseId: Number(damage) } }));
  }
  if (event.target.closest("[data-jcr-damage-new]")) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("damage:open"));
  }
});

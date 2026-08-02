import {
  addDamageCaseNote,
  changeDamageCaseStatus,
  createDamageCase,
  getDamageCase,
  ensureFranchiseCase,
  listDamageCandidates,
  listDamageCases,
  updateDamageCase,
} from "../api.js?v=5";
import { escapeHtml } from "../utils/dom.js";
import { mountAttachments } from "./attachments/component.js?v=2";
import { createAttachmentDraft } from "./attachments/draft-uploader.js";
import { saveEntityWithAttachments } from "./attachments/entity-adapter.js";
import { openOperationalStatusControl } from "./operational-status-control.js";

const STATUS = {
  nuova: "Nuova", in_valutazione: "In valutazione",
  preventivo_richiesto: "Preventivo richiesto",
  preventivo_ricevuto: "Preventivo ricevuto",
  riparazione_programmata: "Riparazione programmata",
  in_riparazione: "In riparazione", chiusa: "Chiusa", annullata: "Annullata",
};
const SEVERITY = { bassa: "Bassa", media: "Media", alta: "Alta", critica: "Critica" };
const VEHICLE = {
  disponibile: "Disponibile",
  disponibile_con_limitazioni: "Disponibile con limitazioni",
  indisponibile: "Indisponibile",
  in_manutenzione: "In manutenzione",
  in_officina: "In officina",
};
const CLOSED = new Set(["chiusa", "annullata"]);
let root;
let allCases = [];
let candidates = [];
let query = "";
const filters = {
  plate: "", status: "all", severity: "all", stopped: "all",
  origin: "all", attachments: "all",
};
let initialized = false;
let selectedCaseId = null;
let damageDraft = null;

function date(value) {
  return value ? new Date(value).toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function money(value) {
  return value == null
    ? "—"
    : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(value);
}

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function refresh() {
  [allCases, candidates] = await Promise.all([
    listDamageCases().then((response) => response.items),
    listDamageCandidates().then((response) => response.items),
  ]);
}

export function sortDamageCases(items) {
  const severityOrder = { critica: 0, alta: 1, media: 2, bassa: 3 };
  return [...items].sort((left, right) => {
    const blocked = ["indisponibile", "in_manutenzione", "in_officina"];
    const leftStopped = blocked.includes(left.asset_availability || left.vehicle_operational_status) ? 0 : 1;
    const rightStopped = blocked.includes(right.asset_availability || right.vehicle_operational_status) ? 0 : 1;
    return leftStopped - rightStopped
      || severityOrder[left.severity] - severityOrder[right.severity]
      || new Date(right.occurred_at) - new Date(left.occurred_at);
  });
}

function filteredCases() {
  const term = query.trim().toLocaleLowerCase("it-IT");
  return sortDamageCases(allCases.filter((item) => {
    const textMatch = !term || [
      item.case_number, item.plate, item.declared_driver, item.description, item.repair_shop,
    ].some((value) => String(value || "").toLocaleLowerCase("it-IT").includes(term));
    const stopped = ["indisponibile", "in_manutenzione", "in_officina"].includes(
      item.asset_availability || item.vehicle_operational_status,
    );
    return textMatch
      && (!filters.plate || String(item.plate || item.external_identifier || "").toLocaleLowerCase("it-IT").includes(filters.plate))
      && (filters.status === "all" || item.status === filters.status)
      && (filters.severity === "all" || item.severity === filters.severity)
      && (filters.stopped === "all" || stopped === (filters.stopped === "yes"))
      && (filters.origin === "all" || item.origin === filters.origin)
      && (filters.attachments === "all" || (Number(item.attachment_count || 0) > 0) === (filters.attachments === "yes"));
  }));
}

function metrics() {
  const open = allCases.filter((item) => !CLOSED.has(item.status));
  return `
    <div class="damage-kpis" aria-label="Indicatori pratiche danno">
      <article><span>Pratiche aperte</span><strong>${open.length}</strong></article>
      <article><span>Da valutare</span><strong>${allCases.filter((item) => ["nuova", "in_valutazione"].includes(item.status)).length}</strong></article>
      <article><span>Veicoli fermi</span><strong>${new Set(allCases.filter((item) => ["indisponibile", "in_manutenzione", "in_officina"].includes(item.asset_availability)).map((item) => item.vehicle_id)).size}</strong></article>
      <article><span>In riparazione</span><strong>${allCases.filter((item) => item.status === "in_riparazione").length}</strong></article>
      <article><span>Chiuse</span><strong>${allCases.filter((item) => item.status === "chiusa").length}</strong></article>
      <article><span>Costo stimato totale</span><strong>${money(allCases.reduce((sum, item) => sum + Number(item.estimated_cost || 0), 0))}</strong></article>
    </div>`;
}

function caseCard(item) {
  return `
    <button type="button" class="damage-case-card severity-${item.severity} ${Number(item.id) === Number(selectedCaseId) ? "selected" : ""}"
      data-damage-case="${item.id}" aria-current="${Number(item.id) === Number(selectedCaseId) ? "true" : "false"}">
      <span class="damage-case-identity"><strong>${escapeHtml(item.case_number)}</strong><small>${escapeHtml(item.vehicle_model || item.external_identifier || "Veicolo")}</small></span>
      <span class="damage-case-plate"><strong>${escapeHtml(item.plate || item.external_identifier)}</strong><small>${escapeHtml(item.declared_driver || "Driver non dichiarato")}</small></span>
      <span class="damage-case-date"><small>Data</small><strong>${escapeHtml(date(item.occurred_at))}</strong></span>
      <span class="damage-case-status">${STATUS[item.status]}</span>
      <span class="damage-case-severity severity-${item.severity}">${SEVERITY[item.severity]}</span>
      <span class="damage-case-vehicle-status">${VEHICLE[item.asset_availability] || VEHICLE[item.vehicle_operational_status]}</span>
      <span class="damage-case-meta"><small>Origine</small>${escapeHtml(item.origin === "journal" ? "Driver Journal" : "Manuale")}</span>
      <span class="damage-case-meta"><small>Fermo mezzo</small>${["indisponibile", "in_manutenzione", "in_officina"].includes(item.asset_availability || item.vehicle_operational_status) ? "Sì" : "No"}</span>
      <span class="damage-case-meta"><small>Costo stimato</small>${escapeHtml(money(item.estimated_cost))}</span>
      <span class="damage-case-meta"><small>Allegati</small>${Number(item.attachment_count || 0)}</span>
      <span class="damage-case-open">Apri →</span>
    </button>`;
}

function renderCaseList() {
  const visible = filteredCases();
  const list = root.querySelector("#damageCaseList");
  if (!list) return;
  root.querySelector("#damageResultCount").textContent = `${visible.length} risultati`;
  list.innerHTML = visible.length
    ? visible.map(caseCard).join("")
    : `<div class="damage-empty">${allCases.length ? "Nessun risultato per i filtri selezionati." : "Nessuna pratica danno. Le nuove anomalie Journal compariranno qui."}</div>`;
}

function renderNavigator() {
  root.classList.remove("damage-detail-mode");
  root.querySelector("#damageMain").innerHTML = `
    ${metrics()}
    <div class="damage-tools">
      <label><span class="visually-hidden">Cerca pratiche</span><input id="damageSearch" type="search" placeholder="Cerca numero pratica, targa, driver o descrizione" value="${escapeHtml(query)}"></label>
      <div class="damage-filters" aria-label="Filtri pratiche">
        <label>Targa<input data-damage-filter="plate" value="${escapeHtml(filters.plate)}" placeholder="Tutte"></label>
        <label>Stato<select data-damage-filter="status"><option value="all">Tutti</option>${Object.entries(STATUS).map(([value,label]) => `<option value="${value}" ${filters.status === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label>Gravità<select data-damage-filter="severity"><option value="all">Tutte</option>${Object.entries(SEVERITY).map(([value,label]) => `<option value="${value}" ${filters.severity === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label>Mezzo fermo<select data-damage-filter="stopped"><option value="all">Tutti</option><option value="yes">Sì</option><option value="no">No</option></select></label>
        <label>Origine<select data-damage-filter="origin"><option value="all">Tutte</option><option value="journal">Driver Journal</option><option value="manual">Manuale</option></select></label>
        <label>Allegati<select data-damage-filter="attachments"><option value="all">Tutti</option><option value="yes">Presenti</option><option value="no">Assenti</option></select></label>
        <button type="button" class="quiet" data-damage-reset>Reset</button>
      </div>
    </div>
    <div id="damageNavigator" class="damage-navigator">
      <aside class="damage-case-navigator" aria-labelledby="damageCasesTitle">
        <div class="damage-section-heading"><h3 id="damageCasesTitle">Pratiche</h3><span id="damageResultCount" class="tag">0 risultati</span></div>
        <div id="damageCaseList" class="damage-case-list"></div>
      </aside>
      <section id="damageDetailPane" class="damage-detail-pane" aria-live="polite">
        <div class="damage-detail-placeholder"><strong>Seleziona una pratica</strong><p>Il dettaglio operativo comparirà in questo pannello.</p></div>
      </section>
    </div>`;
  renderCaseList();
}

function renderShell() {
  root.innerHTML = `
    <header class="damage-header">
      <div><p class="eyebrow">Fleet Operations</p><h2 id="damageWorkspaceTitle">Danni</h2>
      <p class="section-note">Gestione delle pratiche danno del parco mezzi</p></div>
      <div class="damage-actions">
        <button type="button" data-damage-view="candidates">Anomalie da gestire <span class="count-badge">${candidates.length}</span></button>
        <button type="button" class="secondary" data-damage-manual>Nuova pratica danno</button>
      </div>
    </header><div id="damageMain"></div>`;
  renderNavigator();
}

function renderCandidates() {
  root.classList.remove("damage-detail-mode");
  root.querySelector("#damageMain").innerHTML = `
    <button type="button" class="quiet damage-back" data-damage-back>← Pratiche danno</button>
    <div class="damage-section-heading"><div><p class="eyebrow">Driver Journal</p><h3>Anomalie da gestire</h3></div><span class="tag">${candidates.length}</span></div>
    <div class="damage-candidates">${candidates.length ? candidates.map((item) => `
      <article><div><strong>${escapeHtml(item.plate)}</strong><small>${escapeHtml(date(item.occurred_at))}</small></div>
      <p>${escapeHtml(item.description || "Anomalia senza descrizione")}</p>
      <dl><div><dt>Driver</dt><dd>${escapeHtml(item.declared_driver)}</dd></div><div><dt>Foto</dt><dd>${item.photo_count}</dd></div><div><dt>Stato mezzo</dt><dd>${escapeHtml(item.availability)}</dd></div></dl>
      <button type="button" data-create-candidate="${escapeHtml(item.movement_id)}">Crea pratica</button></article>`).join("") : '<div class="damage-empty">Nessuna anomalia da gestire.</div>'}</div>`;
}

function timeline(events) {
  return events.map((event) => `
    <li><time>${escapeHtml(date(event.created_at))}</time>
    <strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong>
    <p>${escapeHtml(event.note || "")}</p><small>${escapeHtml(event.actor)}</small></li>`).join("");
}

async function renderDetail(caseId) {
  const item = await getDamageCase(caseId);
  const media = item.source_movement?.media || [];
  selectedCaseId = Number(caseId);
  root.classList.add("damage-detail-mode");
  renderCaseList();
  root.querySelector("#damageNavigator")?.classList.add("detail-open");
  root.querySelector("#damageDetailPane").innerHTML = `
    <button type="button" class="quiet damage-mobile-back" data-damage-list-back>← Torna alla lista</button>
    <header class="damage-detail-header">
      <div><p class="eyebrow">Pratica danno</p><h3>${escapeHtml(item.case_number)}</h3><p>${escapeHtml(item.plate || item.external_identifier)} · aperta ${escapeHtml(date(item.created_at))}</p></div>
      <div class="damage-detail-badges"><span>${STATUS[item.status]}</span><span>${SEVERITY[item.severity]}</span><span>${VEHICLE[item.asset_availability] || VEHICLE[item.vehicle_operational_status]}</span></div>
    </header>
    <div class="damage-actions">
      <button type="button" class="secondary" data-create-maintenance>Crea manutenzione</button>
      <button type="button" class="secondary" data-open-franchise>Apri Franchigia</button>
      <button type="button" class="secondary" data-open-insurance>Apri Assicurazione</button>
      <button type="button" class="secondary" data-create-rental>Crea noleggio</button>
      <p id="damageMaintenanceStatus" class="section-note" role="status"></p>
    </div>
    <div class="damage-detail-grid">
      <section><h4>Identità pratica ed evento di origine</h4><dl>
        <div><dt>Origine</dt><dd>${escapeHtml(item.origin)}</dd></div>
        <div><dt>Documento</dt><dd>${escapeHtml(item.source_document_id || "Manuale")}</dd></div>
        <div><dt>Driver</dt><dd>${escapeHtml(item.declared_driver || "—")}</dd></div>
        <div><dt>Data evento</dt><dd>${escapeHtml(date(item.occurred_at))}</dd></div>
      </dl></section>
      <section><h4>Descrizione</h4><p>${escapeHtml(item.description)}</p></section>
      <section><h4>Profilo contrattuale del mezzo</h4><dl>
        <div><dt>Tipo contratto</dt><dd>${escapeHtml({
          lungo_termine: "Lungo termine",
          breve_termine: "Breve termine",
          proprieta: "Proprietà",
          leasing: "Leasing",
          altro: "Altro",
        }[item.asset_profile?.contract_type] || "Non configurato")}</dd></div>
        <div><dt>Società</dt><dd>${escapeHtml(item.asset_profile?.company || item.asset_profile?.owner_company || "Non registrata")}</dd></div>
        <div><dt>Numero contratto</dt><dd>${escapeHtml(item.asset_profile?.contract_number || "Non registrato")}</dd></div>
        <div><dt>Franchigia prevista</dt><dd>${item.asset_profile?.deductible == null
          ? "Non prevista"
          : escapeHtml(new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(item.asset_profile.deductible)))}</dd></div>
      </dl></section>
      <section><h4>Stato operativo corrente</h4><dl>
        <div><dt>Motivo stato operativo</dt><dd>${escapeHtml(item.operational_status_reason || "Non registrato")}</dd></div>
        <div><dt>Origine</dt><dd>${escapeHtml(item.operational_status_origin || "Non registrata")}</dd></div>
        <div><dt>Autore</dt><dd>${escapeHtml(item.operational_status_actor || "Non registrato")}</dd></div>
        <div><dt>Aggiornato</dt><dd>${escapeHtml(date(item.operational_status_updated_at))}</dd></div>
      </dl></section>
      <section><h4>Polizza associata</h4><dl>
        <div><dt>Compagnia</dt><dd>${escapeHtml(item.insurance_policy?.company || "Non registrata")}</dd></div>
        <div><dt>Numero polizza</dt><dd>${escapeHtml(item.insurance_policy?.policy_number || "Non registrato")}</dd></div>
        <div><dt>Copertura</dt><dd>${escapeHtml(item.insurance_policy?.coverage_type?.replaceAll("_", " ") || "Non configurata")}</dd></div>
        <div><dt>Scadenza</dt><dd>${escapeHtml(item.insurance_policy?.expires_on || "Non registrata")}</dd></div>
      </dl></section>
      <section><h4>Stato, gravità, valutazione economica e officina</h4>
        <form id="damageAssessmentForm" class="damage-form">
          <label>Gravità<select name="severity">${Object.entries(SEVERITY).map(([key,label]) => `<option value="${key}" ${key === item.severity ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label>Stato operativo<select name="vehicle_operational_status">${Object.entries(VEHICLE).map(([key,label]) => `<option value="${key}" ${key === item.vehicle_operational_status ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label>Motivazione cambio operativo<textarea name="operational_reason" placeholder="Obbligatoria per rimuovere un blocco"></textarea></label>
          <button type="button" class="secondary" data-manual-operational-status>Cambia stato con controllo Fleet</button>
          <label>Officina<input name="repair_shop" value="${escapeHtml(item.repair_shop || "")}"></label>
          <label>Costo stimato EUR<input name="estimated_cost" type="number" min="0" step="0.01" value="${item.estimated_cost || ""}"></label>
          <label>Costo finale EUR<input name="final_cost" type="number" min="0" step="0.01" value="${item.final_cost || ""}"></label>
          <button type="submit">Salva valutazione</button>
        </form>
      </section>
      <section><h4>Media Journal di origine</h4><div class="damage-media">${media.filter((entry) => entry.media_type === "image").map((entry) => `<a href="${escapeHtml(entry.url)}" target="_blank" rel="noreferrer"><img src="${escapeHtml(entry.url)}" alt="Foto anomalia"></a>`).join("") || "<p>Nessun media Journal collegato.</p>"}</div></section>
      <section><h4>Cambio stato</h4><form id="damageStatusForm" class="damage-form"><label>Nuovo stato<select name="status">${Object.entries(STATUS).map(([key,label]) => `<option value="${key}" ${key === item.status ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Stato mezzo alla chiusura<select name="restoration_status"><option value="">Seleziona alla chiusura</option>${Object.entries(VEHICLE).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select></label><label>Motivazione<textarea name="note" required></textarea></label><button type="submit">Registra cambio stato</button></form><p id="damageActionStatus" class="section-note" role="status" aria-live="polite"></p></section>
      <section><h4>Note Fleet Manager</h4><form id="damageNoteForm" class="damage-form"><label>Nuova nota<textarea name="note" required></textarea></label><button type="submit">Aggiungi nota</button></form></section>
      <section class="damage-timeline-section"><h4>Timeline</h4><ol class="damage-timeline">${timeline(item.events)}</ol></section>
      <section><h4>Collegamenti futuri</h4><div class="operational-document-future"><span>Franchigia</span><span>Assicurazione</span><span>Fleet Vision Engine</span><span>PDF</span><span>Firma</span></div></section>
    </div><div data-attachments></div>`;
  await mountAttachments(root.querySelector("[data-attachments]"), {
    entityType: "damage", entityId: item.id,
    title: "Foto, video e documenti della pratica",
  });
  bindDetail(item.id);
}

function bindDetail(caseId) {
  root.querySelector("[data-create-rental]").addEventListener("click", async () => {
    const item = await getDamageCase(caseId);
    document.dispatchEvent(new CustomEvent("rental:open", {
      detail: { preset: {
        vehicle_id: item.vehicle_id, damage_case_id: item.id,
        reason: "danno", notes: `Generato dalla pratica ${item.case_number}`,
      } },
    }));
  });
  root.querySelector("[data-open-insurance]").addEventListener("click", async () => {
    const item = await getDamageCase(caseId);
    document.dispatchEvent(new CustomEvent("insurance:open", {
      detail: item.insurance_policy
        ? { policyId: item.insurance_policy.id }
        : { vehicleId: item.vehicle_id },
    }));
  });
  root.querySelector("[data-open-franchise]").addEventListener("click", async () => {
    const status = root.querySelector("#damageMaintenanceStatus");
    status.textContent = "Apertura valutazione franchigia…";
    try {
      const franchise = await ensureFranchiseCase({ damage_case_id: caseId });
      document.dispatchEvent(new CustomEvent("franchise:open", {
        detail: { franchiseId: franchise.id },
      }));
    } catch (error) {
      status.textContent = error.message;
    }
  });
  root.querySelector("[data-create-maintenance]").addEventListener("click", async () => {
    const item = await getDamageCase(caseId);
    root.querySelector("#damageMaintenanceStatus").textContent =
      "Creazione manutenzione in corso…";
    document.dispatchEvent(new CustomEvent("maintenance:create-from-damage", {
      detail: item,
    }));
  });
  root.querySelector("[data-manual-operational-status]").addEventListener("click", async () => {
    const item = await getDamageCase(caseId);
    openOperationalStatusControl({
      asset: {
        id: item.vehicle_id,
        plate: item.plate,
        availability: item.asset_availability,
      },
      origin: "damage_case",
      linkedCase: item,
      onChanged: async () => {
        await refresh();
        renderNavigator();
        await renderDetail(caseId);
      },
    });
  });
  root.querySelector("#damageAssessmentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    for (const field of ["estimated_cost", "final_cost"]) {
      if (values[field] === "") values[field] = null;
    }
    try {
      const updated = await updateDamageCase(caseId, values);
      document.dispatchEvent(new CustomEvent("fleet:operational-status-changed", { detail: updated }));
      await refresh(); renderNavigator(); await renderDetail(caseId);
    } catch (error) {
      root.querySelector("#damageActionStatus").textContent = error.message;
    }
  });
  root.querySelector("#damageStatusForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const updated = await changeDamageCaseStatus(caseId, formValues(event.currentTarget));
      document.dispatchEvent(new CustomEvent("fleet:operational-status-changed", { detail: updated }));
      await refresh(); renderNavigator(); await renderDetail(caseId);
    } catch (error) {
      root.querySelector("#damageActionStatus").textContent = error.message;
    }
  });
  root.querySelector("#damageNoteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await addDamageCaseNote(caseId, formValues(event.currentTarget));
      await renderDetail(caseId);
    } catch (error) {
      root.querySelector("#damageActionStatus").textContent = error.message;
    }
  });
}

function renderManual() {
  root.classList.remove("damage-detail-mode");
  root.querySelector("#damageMain").innerHTML = `
    <button type="button" class="quiet damage-back" data-damage-back>← Pratiche danno</button>
    <section class="damage-manual"><p class="eyebrow">Inserimento secondario</p><h3>Nuova pratica manuale</h3>
    <form id="damageManualForm" class="damage-form">
      <label>ID veicolo<input name="vehicle_id" type="number" min="1" required></label>
      <label>Data evento<input name="occurred_at" type="datetime-local" required></label>
      <label>Descrizione<textarea name="description" required></textarea></label>
      <label>Motivazione inserimento manuale<textarea name="manual_reason" required></textarea></label>
      <label>Gravità<select name="severity"><option value="bassa">Bassa</option><option value="media" selected>Media</option><option value="alta">Alta</option><option value="critica">Critica</option></select></label>
      <div data-damage-attachment-draft></div>
      <p data-damage-create-status role="status"></p>
      <button type="submit">Crea pratica manuale</button>
    </form></section>`;
  damageDraft = createAttachmentDraft(
    root.querySelector("[data-damage-attachment-draft]"),
    { title: "Foto e video del danno", accept: ".jpg,.jpeg,.png,.webp,.mp4,.mov" },
  );
  root.querySelector("[data-damage-attachment-draft]").addEventListener(
    "attachments:retry",
    () => root.querySelector("#damageManualForm").requestSubmit(),
  );
}

async function createFromCandidate(movementId) {
  const candidate = candidates.find((item) => item.movement_id === movementId);
  const created = await createDamageCase({
    vehicle_id: candidate.vehicle_id, source_movement_id: candidate.movement_id,
    occurred_at: candidate.occurred_at, origin: "journal",
    description: candidate.description || "Anomalia rilevata dal Journal",
    severity: "media",
    vehicle_operational_status: ["maintenance", "in_manutenzione", "in_officina"].includes(candidate.availability) ? "in_officina" : "disponibile",
  });
  await refresh(); renderShell(); await renderDetail(created.id);
}

export async function showDamageWorkspace(options = {}) {
  root = document.getElementById("damageWorkspace");
  document.getElementById("maintenanceWorkspace").hidden = true;
  document.getElementById("documentsWorkspace").hidden = true;
  document.getElementById("franchiseWorkspace").hidden = true;
  document.getElementById("insuranceWorkspace").hidden = true;
  document.getElementById("rentalWorkspace").hidden = true;
  await refresh();
  renderShell();
  root.hidden = false;
  document.getElementById("fleetWorkspaceHome").hidden = true;
  document.getElementById("fleetVehicleDossier").hidden = true;
  if (options.caseId) await renderDetail(Number(options.caseId));
  if (options.movementId) renderCandidates();
  if (initialized) return;
  initialized = true;
  root.addEventListener("input", (event) => {
    if (event.target.id === "damageSearch") query = event.target.value;
    else if (event.target.matches("[data-damage-filter='plate']")) filters.plate = event.target.value.trim().toLocaleLowerCase("it-IT");
    else return;
    renderCaseList();
  });
  root.addEventListener("change", (event) => {
    const key = event.target.dataset.damageFilter;
    if (!key || key === "plate") return;
    filters[key] = event.target.value;
    renderCaseList();
  });
  root.addEventListener("click", async (event) => {
    if (event.target.closest("[data-damage-reset]")) {
      query = "";
      Object.assign(filters, { plate: "", status: "all", severity: "all", stopped: "all", origin: "all", attachments: "all" });
      renderNavigator();
      return;
    }
    const caseId = event.target.closest("[data-damage-case]")?.dataset.damageCase;
    if (caseId) { await renderDetail(Number(caseId)); return; }
    const candidateId = event.target.closest("[data-create-candidate]")?.dataset.createCandidate;
    if (candidateId) { await createFromCandidate(candidateId); return; }
    if (event.target.closest("[data-damage-view='candidates']")) { renderCandidates(); return; }
    if (event.target.closest("[data-damage-manual]")) { renderManual(); return; }
    if (event.target.closest("[data-damage-back]")) renderNavigator();
    if (event.target.closest("[data-damage-list-back]")) {
      root.querySelector("#damageNavigator")?.classList.remove("detail-open");
      root.classList.remove("damage-detail-mode");
    }
  });
  root.addEventListener("submit", async (event) => {
    if (event.target.id !== "damageManualForm") return;
    event.preventDefault();
    const submit = event.target.querySelector("[type='submit']");
    if (submit.disabled) return;
    submit.disabled = true;
    const values = formValues(event.target);
    values.vehicle_id = Number(values.vehicle_id);
    values.origin = "manual";
    values.vehicle_operational_status = "disponibile";
    try {
      const created = await saveEntityWithAttachments({
        draft: damageDraft,
        entityType: "damage",
        saveRecord: () => createDamageCase(values),
      });
      await refresh(); renderShell(); await renderDetail(created.id);
    } catch (error) {
      root.querySelector("[data-damage-create-status]").textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}

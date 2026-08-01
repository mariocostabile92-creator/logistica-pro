import { escapeHtml } from "../../utils/dom.js";
import { documentStatusLabel, documentTypeLabel } from "../documents/status-presenter.js";

const STATUS = {
  disponibile: "Disponibile", disponibile_con_limitazioni: "Disponibile con limitazioni",
  indisponibile: "Indisponibile", in_manutenzione: "In manutenzione",
  in_officina: "In officina", available: "Disponibile",
  reserve: "Disponibile con limitazioni", unavailable: "Indisponibile",
  maintenance: "In manutenzione", workshop: "In officina",
};
const CONTRACT = {
  lungo_termine: "Lungo termine", breve_termine: "Breve termine",
  proprieta: "Proprietà", leasing: "Leasing", altro: "Altro",
};
const ORIGIN = {
  vehicle_library: "Vehicle Library", parco_mezzi: "Fleet Workspace",
  damage_case: "Danno", maintenance: "Manutenzione",
  journal: "Driver Journal", manual: "Aggiornamento manuale",
};

const label = value => String(value || "").replaceAll("_", " ");
const statusLabel = value => STATUS[value] || "Non classificato";
const formatDate = (value, withTime = false) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("it-IT", withTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" });
};
const money = value => value == null ? null : new Intl.NumberFormat(
  "it-IT", { style: "currency", currency: "EUR" },
).format(Number(value));
const row = (term, value) => value == null || value === "" ? "" :
  `<div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>`;
const error = message => message
  ? `<div class="vehicle-section-error" role="alert">${escapeHtml(message)}</div>` : "";
const empty = message => `<div class="vehicle-empty">${escapeHtml(message)}</div>`;
const action = (title, name, id = "") =>
  `<button type="button" class="quiet" data-dossier-action="${name}" data-record-id="${escapeHtml(id)}">${escapeHtml(title)}</button>`;
const fileState = files => files.length
  ? `${files.length} ${files.length === 1 ? "allegato" : "allegati"}`
  : "Nessun allegato";
const expiry = days => days == null ? "Senza scadenza"
  : days < 0 ? `Scaduto da ${Math.abs(days)} giorni`
    : days === 0 ? "Scade oggi" : `Scade tra ${days} giorni`;

function profileSection(model) {
  const profile = model.profile;
  if (!profile) return empty("Profilo contrattuale non ancora configurato.");
  return `<dl class="vehicle-data-grid">
    ${row("Tipo", CONTRACT[profile.contract_type] || label(profile.contract_type))}
    ${row("Azienda", profile.company || profile.owner_company)}
    ${row("Station", model.asset.station)}
    ${row("Numero contratto", profile.contract_number)}
    ${row("Durata", profile.starts_on && profile.expires_on ? `${formatDate(profile.starts_on)} → ${formatDate(profile.expires_on)}` : null)}
    ${row("Immatricolazione", model.asset.registration_date)}
    ${row("Chilometraggio", model.kpis.current_odometer_km == null ? null : `${Number(model.kpis.current_odometer_km).toLocaleString("it-IT")} km`)}
    ${row("Alimentazione", model.asset.fuel_type)}
    ${row("Franchigia", money(profile.deductible))}
    ${row("Fornitore", profile.company)}
  </dl>`;
}

function documentsSection(model) {
  if (!model.documents.length) return empty("Nessun documento registrato.");
  return `<div class="vehicle-record-list">${model.documents.map(item => `
    <article class="vehicle-record">
      <header><div><span class="vehicle-origin">${escapeHtml(documentTypeLabel(item.document_type))}</span>
        <h4>${escapeHtml(item.title)}</h4></div><span class="record-status">${escapeHtml(documentStatusLabel(item.status))}</span></header>
      <dl>${row("Scadenza", item.expires_at ? `${formatDate(item.expires_at)} · ${expiry(item.daysRemaining)}` : "Senza scadenza")}
        ${row("Allegato", item.files.length || item.has_file ? "Disponibile" : "Assente")}
        ${row("Ultimo caricamento", formatDate(item.files[0]?.created_at || item.attachment_uploaded_at, true))}</dl>
      <div class="vehicle-record-actions">
        ${item.files[0]?.preview_url ? `<a href="${escapeHtml(item.files[0].preview_url)}" target="_blank" rel="noopener">Apri allegato</a>` : ""}
        ${action("Apri documento", "document", item.id)}
      </div>
    </article>`).join("")}</div>`;
}

function insuranceSection(model) {
  if (!model.insurance.length) return empty("Nessuna polizza registrata.");
  const ordered = [...model.insurance].sort((a, b) =>
    Number(b.status === "attiva") - Number(a.status === "attiva"));
  return `<div class="vehicle-record-list">${ordered.map(item => `
    <article class="vehicle-record${item.status === "attiva" ? " is-primary" : ""}">
      <header><div><span class="vehicle-origin">${escapeHtml(label(item.coverage_type))}</span>
        <h4>${escapeHtml(item.company)}</h4></div><span class="record-status">${escapeHtml(label(item.status))}</span></header>
      <dl>${row("Numero polizza", item.policy_number)}
        ${row("Periodo", `${formatDate(item.starts_on)} → ${formatDate(item.expires_on)}`)}
        ${row("Residuo", expiry(item.daysRemaining))}
        ${row("Allegati polizza", fileState(item.files))}
        ${row("Ultimo aggiornamento", formatDate(item.updated_at || item.created_at, true))}</dl>
      <div class="vehicle-record-actions">${item.files[0]?.preview_url ? `<a href="${escapeHtml(item.files[0].preview_url)}" target="_blank" rel="noopener">Apri allegato</a>` : ""}
        ${action("Apri polizza", "insurance", item.id)}</div>
    </article>`).join("")}</div>`;
}

function rentalsSection(model) {
  if (!model.rentals.length) return empty("Nessun noleggio registrato.");
  return `<div class="vehicle-record-list">${model.rentals.map(item => `
    <article class="vehicle-record"><header><div><span class="vehicle-origin">Noleggio</span>
      <h4>${escapeHtml(item.rental_company)}</h4></div><span class="record-status">${escapeHtml(label(item.status))}</span></header>
      <dl>${row("Contratto", item.contract_number)}
        ${row("Mezzo sostitutivo", item.replacement_vehicle)}
        ${row("Periodo", `${formatDate(item.start_date)} → ${formatDate(item.end_date || item.expected_end_date)}`)}
        ${row("Residuo", expiry(item.daysRemaining))}
        ${row("Contratto allegato", fileState(item.files))}</dl>
      <div class="vehicle-record-actions">${item.files[0]?.preview_url ? `<a href="${escapeHtml(item.files[0].preview_url)}" target="_blank" rel="noopener">Apri contratto</a>` : ""}
        ${action("Apri noleggio", "rental", item.id)}</div>
    </article>`).join("")}</div>`;
}

function maintenanceSection(model) {
  if (!model.maintenances.length) return empty("Nessuna manutenzione registrata.");
  const open = model.maintenances.filter(item => item.open);
  const completed = model.maintenances.find(item => item.status === "completata");
  const next = open.find(item => item.expected_at);
  return `<div class="vehicle-section-summary">
    <strong>${open.length} aperte</strong>
    <span>Ultima conclusa: ${escapeHtml(completed?.maintenance_number || "nessuna")}</span>
    <span>Prossima prevista: ${escapeHtml(formatDate(next?.expected_at, true) || "non programmata")}</span>
  </div><div class="vehicle-record-list">${model.maintenances.map(item => `
    <article class="vehicle-record"><header><div><span class="vehicle-origin">${escapeHtml(label(item.maintenance_type))}</span>
      <h4>${escapeHtml(item.maintenance_number)}</h4></div><span class="record-status">${escapeHtml(label(item.status))}</span></header>
      <dl>${row("Officina", item.repair_shop)}
        ${row("Apertura", formatDate(item.opened_at, true))}
        ${row("Data prevista", formatDate(item.expected_at, true))}
        ${row("Allegati", fileState(item.files))}
        ${row("Stato mezzo collegato", statusLabel(model.asset.operational_status || model.asset.availability))}</dl>
      <div class="vehicle-record-actions">${action("Apri manutenzione", "maintenance", item.id)}</div>
    </article>`).join("")}</div>`;
}

function damageSection(model) {
  if (!model.damages.length) return empty("Nessuna pratica danno registrata.");
  return `<div class="vehicle-section-summary"><strong>${model.openDamages.length} aperte</strong>
    <span>${model.closedDamages.length} chiuse</span></div>
    <div class="vehicle-record-list">${model.damages.map(item => `
      <article class="vehicle-record"><header><div><span class="vehicle-origin">${escapeHtml(item.case_number)}</span>
        <h4>${escapeHtml(item.description)}</h4></div><span class="record-status severity-${escapeHtml(item.severity)}">${escapeHtml(label(item.severity))}</span></header>
        <dl>${row("Stato", label(item.status))}
          ${row("Data", formatDate(item.occurred_at, true))}
          ${row("Driver", item.declared_driver_identifier)}
          ${row("Media", `${item.photos} foto · ${item.videos} video`)}</dl>
        ${item.attachments.find(file => file.mime_type.startsWith("image/")) ? `<img class="vehicle-damage-thumb" src="${escapeHtml(item.attachments.find(file => file.mime_type.startsWith("image/")).preview_url)}" alt="Ultima foto pratica ${escapeHtml(item.case_number)}">` : ""}
        <div class="vehicle-record-actions">${action("Apri pratica", "damage", item.id)}</div>
      </article>`).join("")}</div>`;
}

function journalCard(title, item) {
  if (!item) return `<article class="vehicle-journal-card">${empty(`${title}: nessuna registrazione.`)}</article>`;
  return `<article class="vehicle-journal-card"><span class="vehicle-origin">${escapeHtml(title)}</span>
    <h4>${escapeHtml(item.declared_driver_identifier || "Driver non indicato")}</h4>
    <time>${escapeHtml(formatDate(item.occurred_at, true))}</time>
    <dl>${row("Chilometraggio", `${Number(item.odometer_km).toLocaleString("it-IT")} km`)}
      ${row("Carburante", item.fuel_percentage == null ? null : `${item.fuel_percentage}%`)}
      ${row("Anomalia", item.anomaly_present ? item.anomaly_description || "Segnalata" : "Nessuna")}</dl>
  </article>`;
}

export function renderVehicleDossierExcellence(container, model) {
  const asset = model.asset;
  const vision = model.vision;
  const decisions = vision?.decisions || [];
  const actions = vision?.actions || [];
  const topDecision = decisions[0];
  const topAction = actions[0];
  container.innerHTML = `
    <div class="vehicle-hero">
      <button type="button" class="quiet" data-dossier-action="back">← Vehicle Library</button>
      <div class="vehicle-hero-main"><div><p class="eyebrow">Dossier operativo</p>
        <h2>${escapeHtml(asset.plate || asset.external_identifier)}</h2>
        <p class="vehicle-model">${escapeHtml(asset.category || model.journalAsset.model || "Modello non registrato")}</p></div>
        <span class="vehicle-status-badge">${escapeHtml(statusLabel(asset.operational_status || asset.availability))}</span></div>
      <dl class="vehicle-hero-facts">
        ${row("Disponibilità", statusLabel(asset.availability))}
        ${row("Motivo", asset.operational_status_reason)}
        ${row("Chilometraggio", model.kpis.current_odometer_km == null ? null : `${Number(model.kpis.current_odometer_km).toLocaleString("it-IT")} km`)}
        ${row("Ultimo aggiornamento", formatDate(asset.operational_status_updated_at || asset.updated_at, true))}
        ${row("Azienda", asset.profile?.company || asset.profile?.owner_company)}
        ${row("Station", asset.station)}
      </dl>
    </div>

    <div class="vehicle-dossier-grid">
      <section class="vehicle-dossier-section" data-section="profile">
        <header><div><p class="eyebrow">Identità economica</p><h3>Profilo mezzo</h3></div>
          ${action("Modifica profilo", "profile")}</header>${profileSection(model)}
      </section>
      <section class="vehicle-dossier-section" data-section="status">
        <header><div><p class="eyebrow">Fonte operativa</p><h3>Stato operativo</h3></div>
          ${action("Cambia stato", "status")}</header>
        <dl class="vehicle-data-grid">
          ${row("Stato attuale", statusLabel(asset.operational_status || asset.availability))}
          ${row("Disponibilità", statusLabel(asset.availability))}
          ${row("Motivo operativo", asset.operational_status_reason)}
          ${row("Da quanto", vision?.days_stopped == null ? "Operativo" : `${vision.days_stopped} giorni`)}
          ${row("Ultimo cambio", formatDate(asset.operational_status_updated_at, true))}
          ${row("Origine", ORIGIN[asset.operational_status_origin] || label(asset.operational_status_origin))}
        </dl>
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="documents">
        <header><div><p class="eyebrow">Archivio</p><h3>Documenti</h3></div>
          ${action("Vai a Documenti", "documents")}</header>${error(model.errors.documents)}${documentsSection(model)}
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="insurance">
        <header><div><p class="eyebrow">Coperture</p><h3>Assicurazioni</h3></div>
          ${action("Vai ad Assicurazioni", "insurances")}</header>${error(model.errors.insurance)}${insuranceSection(model)}
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="rentals">
        <header><div><p class="eyebrow">Contratti temporanei</p><h3>Noleggi</h3></div>
          ${action("Vai a Noleggi", "rentals")}</header>${error(model.errors.rentals)}${rentalsSection(model)}
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="maintenances">
        <header><div><p class="eyebrow">Interventi</p><h3>Manutenzioni</h3></div>
          ${action("Vai a Manutenzioni", "maintenances")}</header>${error(model.errors.maintenances)}${maintenanceSection(model)}
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="damages">
        <header><div><p class="eyebrow">Pratiche</p><h3>Danni</h3></div>
          ${action("Vai a Danni", "damages")}</header>${error(model.errors.damages)}${damageSection(model)}
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="journal">
        <header><div><p class="eyebrow">GDB</p><h3>Driver Journal</h3></div>
          ${action("Vai al Journal", "journal")}</header>
        <div class="vehicle-journal-grid">${journalCard("Ultima presa in carico", model.lastCheckout)}
          ${journalCard("Ultimo rientro", model.lastCheckin)}</div>
        <p class="vehicle-session-state">Stato ultima sessione: ${model.movements[0] ? "Completata" : "Nessuna sessione"} · Origine: ${escapeHtml(model.movements[0]?.source || "storico")}</p>
      </section>
      <section class="vehicle-dossier-section vehicle-section-wide" data-section="timeline">
        <header><div><p class="eyebrow">Cronologia aggregata</p><h3>Storico operativo</h3></div></header>
        <div id="fleetDossierUnifiedTimeline"></div>
        <div id="fleetDossierAttachments"></div>
      </section>
      <section class="vehicle-dossier-section" data-section="vision">
        <header><div><p class="eyebrow">Analisi verificabile</p><h3>Fleet Vision</h3></div>
          ${action("Apri Fleet Vision", "vision")}</header>
        ${vision ? `<dl class="vehicle-data-grid">${row("Stato generale", statusLabel(vision.operational_status))}
          ${row("Criticità", String(decisions.length))}
          ${row("Più importante", topDecision?.title)}
          ${row("Ultima elaborazione", formatDate(asset.updated_at, true))}</dl>
          <div class="vehicle-warning-list">${decisions.slice(0, 3).map(item => `<span>${escapeHtml(item.title)}</span>`).join("")}
            ${decisions.length > 3 ? `<strong>+ ${decisions.length - 3} altre criticità</strong>` : ""}</div>`
          : empty("Fleet Vision temporaneamente non disponibile.")}
      </section>
      <section class="vehicle-dossier-section" data-section="brain">
        <header><div><p class="eyebrow">Decision Center</p><h3>Fleet Brain / Action Center</h3></div>
          ${action("Apri Action Center", "action-center")}</header>
        ${topAction ? `<dl class="vehicle-data-grid">${row("Decisioni aperte", String(decisions.length))}
          ${row("Decisione prioritaria", topDecision?.title)}
          ${row("Azione suggerita", topAction.title)}
          ${row("Motivazione", topAction.motivation)}</dl>`
          : empty("Nessuna azione operativa aperta per il mezzo.")}
      </section>
    </div>`;
}

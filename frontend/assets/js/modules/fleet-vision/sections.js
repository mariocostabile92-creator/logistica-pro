import { escapeHtml } from "../../utils/dom.js";
import { directActionLabel } from "./navigation.js";
import { fleetVisionState, filteredCriticalities } from "./state.js";

const domainLabel = {
  damage: "Danni", maintenance: "Manutenzioni", documents: "Documenti",
  insurance: "Assicurazioni", rentals: "Noleggi", journal: "Driver Journal",
  library: "Fleet Workspace", vision: "Fleet Vision", franchises: "Franchigie",
};
const priorityLabel = { alta: "Critiche", media: "Importanti", bassa: "Informative" };
const dateLabel = value => value
  ? new Date(value).toLocaleDateString("it-IT") : "Data non disponibile";

export function snapshotSection(summary) {
  const kpis = [
    ["operational", "Mezzi operativi", "library"],
    ["unavailable", "Mezzi indisponibili", "availability"],
    ["in_maintenance", "Mezzi in manutenzione", "maintenance"],
    ["open_damages", "Pratiche danno aperte", "damage"],
    ["open_maintenances", "Manutenzioni aperte", "maintenance"],
    ["documents_registered", "Documenti registrati", "documents"],
    ["insurance_policies", "Polizze collegate", "insurance"],
    ["open_franchises", "Franchigie aperte", "franchises"],
    ["active_rentals", "Noleggi attivi", "rentals"],
    ["missing_documents", "Documenti mancanti", "documents"],
    ["expiring_contracts", "Contratti in scadenza", "library"],
    ["expiring_insurance", "Assicurazioni in scadenza", "insurance"],
    ["journal_incomplete", "Driver Journal incompleti", "journal"],
  ];
  return `<section class="fve2-section fve2-snapshot" aria-labelledby="fveSnapshotTitle">
    <header><p class="eyebrow">Fleet Snapshot</p><h3 id="fveSnapshotTitle">Stato della flotta</h3></header>
    <div>${kpis.map(([key, label, filter]) => `<button type="button" class="fve2-kpi" data-fve-filter="${filter}">
      <strong>${summary[key] ?? 0}</strong><span>${escapeHtml(label)}</span>
      <small>Apri dettaglio</small></button>`).join("")}</div>
  </section>`;
}

const deadlineCriticalityLabel = {
  critica: "Critica", alta: "Alta", media: "Media", regolare: "Regolare",
};

export function upcomingDeadlinesSection(categories) {
  return `<section class="fve2-section fve2-deadlines" aria-labelledby="fveDeadlinesTitle">
    <header><p class="eyebrow">Priorità temporali</p><h3 id="fveDeadlinesTitle">Prossime scadenze</h3>
      <p>Le urgenze sono aggregate dalle fonti operative. Il dettaglio resta nel workspace di origine.</p></header>
    <div>${categories.map(item => {
      const nearest = item.nearest;
      const vehicle = nearest?.plate || nearest?.external_identifier;
      return `<article class="fve2-deadline-card criticality-${escapeHtml(item.criticality)}">
        <header><div><span>${escapeHtml(item.label)}</span><strong>${item.count}</strong></div>
          <span class="fve2-deadline-level">${escapeHtml(deadlineCriticalityLabel[item.criticality])}</span></header>
        <dl><div><dt>Più urgente</dt><dd>${escapeHtml(nearest?.title || "Nessuna scadenza entro 30 giorni")}</dd></div>
          <div><dt>Mezzo</dt><dd>${escapeHtml(vehicle || "—")}</dd></div>
          <div><dt>Prossima data</dt><dd>${escapeHtml(dateLabel(nearest?.due_date))}</dd></div></dl>
        <button type="button" class="fve2-deadline-action" data-fve-deadline-source="${escapeHtml(item.module)}"
          data-fve-deadline-ids="${item.source_ids.join(",")}">Apri ${escapeHtml(item.label)}</button>
      </article>`;
    }).join("")}</div>
  </section>`;
}

function criticalityCard(item) {
  const actions = item.actions?.length ? item.actions : [{
    module: item.module, label: directActionLabel(item),
  }];
  return `<article class="fve2-criticality priority-${item.priority}">
    <header><div><span class="fve2-origin">Origine · ${escapeHtml(item.origin || domainLabel[item.module] || item.module)}</span>
      <h5>${escapeHtml(item.title)}</h5></div><span class="fve2-level">${escapeHtml(priorityLabel[item.priority])}</span></header>
    <dl><div><dt>Veicolo</dt><dd>${escapeHtml(item.vehicle)}</dd></div>
      <div><dt>Data</dt><dd>${escapeHtml(dateLabel(item.date))}</dd></div>
      <div><dt>Stato</dt><dd>${escapeHtml(item.status)}</dd></div></dl>
    <p><strong>Perché?</strong> ${escapeHtml(item.description)}</p>
    <div class="fve2-criticality-actions">${actions.map(action => `<button type="button" class="quiet"
      data-fve-source="${escapeHtml(action.module)}" data-fve-vehicle-id="${item.vehicle_id}"
      data-fve-record-id="${item.record_id || ""}" data-fve-driver-id="${escapeHtml(item.driver_id || "")}">
      ${escapeHtml(action.label)}</button>`).join("")}</div>
  </article>`;
}

function vehicleGroup(group, items) {
  const open = fleetVisionState.expandedVehicles.has(group.vehicle_id);
  const level = priorityLabel[items[0]?.priority] || "Informative";
  return `<article class="fve2-vehicle-group">
    <button type="button" class="fve2-vehicle-toggle" data-fve-vehicle-toggle="${group.vehicle_id}"
      aria-expanded="${open}"><span><strong>${escapeHtml(group.vehicle)}</strong>
      <small>${items.length} criticità · livello ${escapeHtml(level)}</small></span>
      <span class="fve2-expand-label"><b aria-hidden="true">${open ? "−" : "+"}</b>${open ? "Riduci" : "Espandi"}</span></button>
    ${open ? `<div class="fve2-vehicle-criticalities">${items.map(criticalityCard).join("")}</div>` : ""}
  </article>`;
}

export function criticalitiesSection() {
  const filtered = filteredCriticalities();
  const groups = ["alta", "media", "bassa"].map(priority => ({
    priority,
    items: filtered.filter(item => item.priority === priority),
  }));
  return `<section class="fve2-section fve2-criticalities" aria-labelledby="fveCriticalitiesTitle">
    <header><p class="eyebrow">Criticità</p><h3 id="fveCriticalitiesTitle">Cosa richiede attenzione</h3>
      <div class="fve2-filters" aria-label="Filtri criticità">${[
        ["all", "Tutti"], ["alta", "Critiche"], ["documents", "Documenti"],
        ["insurance", "Assicurazioni"], ["rentals", "Noleggi"], ["damage", "Danni"],
        ["maintenance", "Manutenzioni"], ["franchises", "Franchigie"],
        ["journal", "Driver Journal"],
        ["availability", "Disponibilità"],
      ].map(([key, label]) => `<button type="button" class="${fleetVisionState.filter === key ? "active" : ""}"
        data-fve-filter="${key}" aria-pressed="${fleetVisionState.filter === key}">${label}</button>`).join("")}</div>
    </header>
    ${filtered.length ? groups.map(group => {
      const open = fleetVisionState.expandedGroups.has(group.priority);
      const visible = fleetVisionState.showAll.has(group.priority) ? group.items : group.items.slice(0, 5);
      const byVehicle = Object.values(visible.reduce((acc, item) => {
        acc[item.vehicle_id] ||= { vehicle_id: item.vehicle_id, vehicle: item.vehicle, items: [] };
        acc[item.vehicle_id].items.push(item); return acc;
      }, {}));
      return `<section class="fve2-priority-group priority-${group.priority}"><button type="button" data-fve-group="${group.priority}"
        aria-expanded="${open}"><span><b aria-hidden="true">${open ? "▾" : "▸"}</b>${priorityLabel[group.priority]}</span><strong>${group.items.length}</strong></button>
        ${open ? `<div>${group.items.length ? byVehicle.map(v => vehicleGroup(v, v.items)).join("")
          : `<div class="view-state">Nessuna criticità in questo gruppo.</div>`}
          ${group.items.length > 5 && !fleetVisionState.showAll.has(group.priority)
            ? `<button type="button" class="quiet" data-fve-show-all="${group.priority}">Mostra tutte</button>` : ""}</div>` : ""}
      </section>`;
    }).join("") : `<div class="view-state"><strong>Nessuna criticità operativa rilevata.</strong><p>Non risultano condizioni da evidenziare per il filtro selezionato.</p></div>`}
  </section>`;
}

export function operationsSection(data) {
  const latest = key => data.items.map(item => item.latest?.[key]?.occurred_at
    || item.latest?.[key]?.opened_at).filter(Boolean).sort().at(-1);
  const rows = [
    ["Documentazione", data.summary.missing_documents ? "Da verificare" : `${data.summary.documents_registered} registrati`, latest("use"), "documents"],
    ["Assicurazioni", data.summary.expired_insurance || data.summary.expiring_insurance ? "Da verificare" : `${data.summary.insurance_policies} collegate`, null, "insurance"],
    ["Driver Journal", data.summary.journal_incomplete ? "Sessioni incomplete" : "Regolare", latest("use"), "journal"],
    ["Manutenzioni", data.summary.open_maintenances ? "Interventi aperti" : "Regolare", latest("maintenance"), "maintenance"],
    ["Danni", data.summary.open_damages ? "Pratiche aperte" : "Regolare", latest("damage"), "damage"],
    ["Franchigie", data.summary.open_franchises ? "Valutazioni aperte" : "Regolare", null, "franchises"],
    ["Noleggi", data.summary.active_rentals ? "Noleggi attivi" : "Regolare", null, "rentals"],
    ["Disponibilità", data.summary.unavailable || data.summary.in_maintenance ? "Attenzione" : "Regolare", latest("status_change"), "library"],
    ["Contratti", data.summary.expiring_contracts ? "In scadenza" : "Regolare", null, "library"],
  ];
  return `<section class="fve2-section fve2-operations" aria-labelledby="fveOperationsTitle">
    <header><p class="eyebrow">Operatività</p><h3 id="fveOperationsTitle">Indicatori sintetici</h3></header>
    <div>${rows.map(([label, status, updated, module]) => `<article><div><h4>${label}</h4>
      <span class="fve2-operation-status">${status}</span><small>Ultimo aggiornamento · ${dateLabel(updated)}</small></div>
      <button type="button" class="fve2-open-action" data-fve-source="${module}">Apri</button></article>`).join("")}</div>
  </section>`;
}

export function quickAccessSection() {
  const links = [
    ["library", "Apri Vehicle Library"], ["documents", "Apri Documenti"],
    ["insurance", "Apri Assicurazioni"], ["rentals", "Apri Noleggi"],
    ["damage", "Apri Danni"], ["franchises", "Apri Franchigie"],
    ["maintenance", "Apri Manutenzioni"], ["journal", "Apri Driver Journal"],
    ["brain", "Apri Fleet Brain"],
  ];
  return `<section class="fve2-section fve2-quick" aria-labelledby="fveQuickTitle">
    <header><p class="eyebrow">Accessi rapidi</p><h3 id="fveQuickTitle">Apri il workspace sorgente</h3></header>
    <div>${links.map(([module, label]) => `<button type="button" class="fve2-quick-action"
      data-fve-source="${module}">${label}</button>`).join("")}</div>
  </section>`;
}

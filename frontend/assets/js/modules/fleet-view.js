import {
  byId,
  escapeHtml,
  renderViewState,
  showDataView,
} from "../utils/dom.js";
import { assetValueLabel } from "../utils/formatters.js";
import { mountOperationalDocumentHistory } from "./vehicle-library/operational-documents.js";


function documentLabel(document) {
  const expiry = document.expires_on ? ` · scade ${document.expires_on}` : "";
  return `${assetValueLabel(document.document_type)}${expiry}`;
}


function eventLabel(eventType) {
  const labels = {
    AssetCreated: "Asset creato",
    AssetUpdated: "Asset aggiornato",
    AssetAvailable: "Asset disponibile",
    AssetUnavailable: "Asset non disponibile",
    AssetMaintenanceStarted: "Ingresso in officina",
    AssetMaintenanceEnded: "Uscita dall'officina",
    AssetAvailabilityChanged: "Disponibilità modificata",
    AssetAvailabilityObserved: "Disponibilità osservata",
    AssetDocumentAdded: "Documento aggiunto",
    AssetReserveAssigned: "Mezzo assegnato alla riserva",
    AssetDocumentObserved: "Documento osservato",
    AssetAssociationChanged: "Driver associato aggiornato",
  };
  return labels[eventType] || assetValueLabel(eventType);
}


function timestamp(value) {
  if (!value) return "Non registrato";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
}


export function availabilityPresentation(value) {
  const key = String(value || "").trim().toLowerCase();
  return {
    available: { label: "Disponibile", tone: "available" },
    disponibile: { label: "Disponibile", tone: "available" },
    disponibile_con_limitazioni: { label: "Disponibile con limitazioni", tone: "reserve" },
    maintenance: { label: "Officina", tone: "maintenance" },
    in_manutenzione: { label: "In manutenzione", tone: "maintenance" },
    in_officina: { label: "In officina", tone: "maintenance" },
    unavailable: { label: "Indisponibile", tone: "unavailable" },
    indisponibile: { label: "Indisponibile", tone: "unavailable" },
    reserve: { label: "Riserva", tone: "reserve" },
  }[key] || { label: "Da verificare", tone: "unknown" };
}


export function fleetDriverLabel(asset, events = []) {
  const directValue = [
    asset.driver_name,
    asset.assigned_driver,
    asset.driver,
    asset.observed_assigned_human_resource,
  ].find((value) => typeof value === "string" && value.trim());
  if (directValue) return directValue.trim();

  const chronologicalEvents = [...events].sort(
    (left, right) => new Date(right.occurred_at) - new Date(left.occurred_at),
  );
  for (const event of chronologicalEvents) {
    const association = event.details?.changes?.observed_assigned_human_resource;
    const value = association?.after;
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "Non associato";
}


function statusBadge(asset) {
  const status = availabilityPresentation(asset.availability);
  return `
    <span class="fleet-status-badge fleet-status-${status.tone}">
      <span class="fleet-status-dot" aria-hidden="true"></span>
      ${escapeHtml(status.label)}
    </span>
  `;
}


export function fleetSummary(assets, today = new Date()) {
  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() + 30);
  const normalizedCutoff = cutoff.toISOString().slice(0, 10);
  let documentsAttention = 0;
  for (const asset of assets) {
    for (const document of asset.documents || []) {
      if (document.expires_on && document.expires_on <= normalizedCutoff) {
        documentsAttention += 1;
      }
    }
  }
  const countAvailability = (...values) => assets.filter(
    (asset) => values.includes(asset.availability),
  ).length;
  return {
    total: assets.length,
    available: countAvailability("available", "disponibile"),
    reserve: countAvailability("reserve", "disponibile_con_limitazioni"),
    maintenance: countAvailability("maintenance", "in_manutenzione", "in_officina"),
    unavailable: countAvailability("unavailable", "indisponibile"),
    documentsAttention,
  };
}


export function setFleetMetricPriority(id, value, positivePriority = "attention") {
  const metric = byId(id).closest("div");
  if (!metric) return;
  metric.dataset.priority = Number(value) > 0 ? positivePriority : "normal";
}


function renderFleetSummary(assets) {
  const summary = fleetSummary(assets);
  byId("fleetTotalAssets").textContent = summary.total;
  byId("fleetAvailableAssets").textContent = summary.available;
  byId("fleetUnavailableAssets").textContent = summary.unavailable;
  byId("fleetReserveAssets").textContent = summary.reserve;
  byId("fleetMaintenanceAssets").textContent = summary.maintenance;
  byId("fleetDocumentsAttention").textContent = summary.documentsAttention;
  byId("fleetLongTermAssets").textContent = assets.filter(
    (asset) => asset.profile?.contract_type === "lungo_termine",
  ).length;
  byId("fleetShortTermAssets").textContent = assets.filter(
    (asset) => asset.profile?.contract_type === "breve_termine",
  ).length;
  byId("fleetOwnedAssets").textContent = assets.filter(
    (asset) => asset.profile?.contract_type === "proprieta",
  ).length;
  setFleetMetricPriority("fleetTotalAssets", 0);
  setFleetMetricPriority("fleetAvailableAssets", 0);
  setFleetMetricPriority("fleetMaintenanceAssets", summary.maintenance);
  setFleetMetricPriority("fleetUnavailableAssets", summary.unavailable, "critical");
  setFleetMetricPriority("fleetDocumentsAttention", summary.documentsAttention);
}


export function filterFleetAssets(assets, query) {
  const normalized = String(query || "").trim().toLocaleLowerCase("it-IT");
  if (!normalized) return assets;
  return assets.filter((asset) => [
    asset.plate,
    asset.external_identifier,
    asset.category,
    asset.status,
    availabilityPresentation(asset.availability).label,
    fleetDriverLabel(asset),
  ].some((value) => String(value || "").toLocaleLowerCase("it-IT").includes(normalized)));
}


function assetRow(asset) {
  const primaryIdentifier = asset.plate || asset.external_identifier;
  const driver = fleetDriverLabel(asset);
  const category = assetValueLabel(asset.category) || "Non indicata";
  const updatedAt = timestamp(asset.updated_at);
  const operationalDetail = operationalStatusDetail(asset);
  return `
    <tr data-fleet-action="select" data-asset-id="${asset.id}" tabindex="0" aria-label="Apri scheda mezzo ${escapeHtml(primaryIdentifier)}">
      <td>
        <strong>${escapeHtml(primaryIdentifier)}</strong>
      </td>
      <td>${statusBadge(asset)}
        ${operationalDetail}
        <button type="button" class="quiet" data-operational-status-asset="${asset.id}">
          Modifica stato operativo
        </button>
      </td>
      <td><span class="fleet-secondary-value${driver === "Non associato" ? " is-missing" : ""}">${escapeHtml(driver)}</span></td>
      <td><span class="fleet-secondary-value${category === "Non indicata" ? " is-missing" : ""}">${escapeHtml(category)}</span></td>
      <td><span class="fleet-secondary-value fleet-timestamp${updatedAt === "Non registrato" ? " is-missing" : ""}">${escapeHtml(updatedAt)}</span></td>
    </tr>
  `;
}


function assetCard(asset) {
  const primaryIdentifier = asset.plate || asset.external_identifier;
  const driver = fleetDriverLabel(asset);
  const category = assetValueLabel(asset.category) || "Non indicata";
  const updatedAt = timestamp(asset.updated_at);
  const operationalDetail = operationalStatusDetail(asset);
  return `
    <button type="button" class="fleet-asset-card" data-fleet-action="select" data-asset-id="${asset.id}" aria-label="Apri scheda mezzo ${escapeHtml(primaryIdentifier)}">
      <span class="fleet-card-heading">
        <strong>${escapeHtml(primaryIdentifier)}</strong>
        ${statusBadge(asset)}
      </span>
      ${operationalDetail}
      <span class="fleet-card-grid">
        <span><small>Driver associato</small><strong class="fleet-secondary-value${driver === "Non associato" ? " is-missing" : ""}">${escapeHtml(driver)}</strong></span>
        <span><small>Categoria</small><strong class="fleet-secondary-value${category === "Non indicata" ? " is-missing" : ""}">${escapeHtml(category)}</strong></span>
        <span class="fleet-card-updated"><small>Aggiornato</small><strong class="fleet-secondary-value fleet-timestamp${updatedAt === "Non registrato" ? " is-missing" : ""}">${escapeHtml(updatedAt)}</strong></span>
      </span>
    </button>
  `;
}


export function fleetRegistryCsv(assets) {
  const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const rows = assets.map((asset) => [
    asset.plate || asset.external_identifier,
    availabilityPresentation(asset.availability).label,
    fleetDriverLabel(asset),
    assetValueLabel(asset.category) || "",
    timestamp(asset.updated_at),
  ]);
  return [
    ["Targa", "Stato", "Driver associato", "Categoria", "Ultimo aggiornamento"],
    ...rows,
  ].map((row) => row.map(escapeCsv).join(",")).join("\r\n");
}


export function renderAssetList(
  assets,
  { demoEnabled = false, allAssets = assets, searchTerm = "" } = {},
) {
  const tableBody = byId("fleetAssetTableBody");
  const cards = byId("fleetAssetCards");
  if (!allAssets.length) {
    byId("createAssetBtn").hidden = true;
    byId("fleetExportBtn").disabled = true;
    showDataView("fleetViewState", "fleetDataView", false);
    renderViewState(byId("fleetViewState"), {
      state: "empty",
      title: "Nessun mezzo registrato",
      description: "Importa lo stato del parco per iniziare a lavorare sul Registry.",
      actionLabel: "Importa Stato Parco",
      action: "sync-fleet",
      actionTone: "primary",
      secondaryActionLabel: demoEnabled ? "Carica demo" : "",
      secondaryAction: demoEnabled ? "load-demo" : "",
      visual: "fleet",
    });
    return;
  }

  byId("createAssetBtn").hidden = false;
  byId("fleetExportBtn").disabled = false;
  showDataView("fleetViewState", "fleetDataView", true);
  renderFleetSummary(allAssets);
  byId("fleetRegistryCount").textContent = searchTerm
    ? `${assets.length} di ${allAssets.length} mezzi`
    : `${allAssets.length} ${allAssets.length === 1 ? "mezzo" : "mezzi"}`;
  if (!assets.length) {
    tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">Nessun mezzo corrisponde alla ricerca.</td></tr>';
    cards.innerHTML = '<p class="empty-state">Nessun mezzo corrisponde alla ricerca.</p>';
    return;
  }
  tableBody.innerHTML = assets.map(assetRow).join("");
  cards.innerHTML = assets.map(assetCard).join("");
}

function operationalStatusDetail(asset) {
  const presentation = availabilityPresentation(asset.availability);
  if (presentation.tone === "available" || !asset.operational_status_reason) return "";
  const detail = `${asset.operational_status_reason} · ${dossierTimestamp(
    asset.operational_status_updated_at,
  )}`;
  return `<span class="fleet-operational-reason" title="${escapeHtml(detail)}">${escapeHtml(detail)}</span>`;
}


export function renderFleetTree(assets, selectedAssetId = null) {
  byId("fleetTreeCount").textContent = assets.length;
  byId("fleetTreeAssets").innerHTML = assets.length
    ? assets.map((asset) => {
        const identifier = asset.plate || asset.external_identifier;
        const selected = Number(selectedAssetId) === Number(asset.id);
        return `
          <button
            type="button"
            class="fleet-tree-asset${selected ? " selected" : ""}"
            data-fleet-tree-asset="${asset.id}"
            role="treeitem"
            aria-selected="${selected}"
          >
            <span aria-hidden="true">▰</span>
            <span>${escapeHtml(identifier)}</span>
          </button>
        `;
      }).join("")
    : '<p class="fleet-tree-empty">Nessun mezzo</p>';
}


function dossierTimestamp(value) {
  if (!value) return "Non registrato";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT", {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

const CONTRACT_TYPE = Object.freeze({
  lungo_termine: "Lungo termine",
  breve_termine: "Breve termine",
  proprieta: "Proprietà",
  leasing: "Leasing",
  altro: "Altro",
});
const CONTRACT_STATUS = Object.freeze({
  attivo: "Attivo",
  in_scadenza: "In scadenza",
  scaduto: "Scaduto",
});

function money(value) {
  if (value == null || value === "") return "Non registrato";
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value));
}

function renderContractProfile(profile) {
  const target = byId("fleetProfileSummary");
  if (!profile) {
    target.innerHTML = '<div><dt>Profilo</dt><dd>Non ancora configurato</dd></div>';
    return;
  }
  if (profile.contract_type === "proprieta") {
    target.innerHTML = [
      ["Tipo contratto", CONTRACT_TYPE[profile.contract_type]],
      ["Società proprietaria", profile.owner_company || "Non registrata"],
      ["Data acquisto", profile.purchased_on || "Non registrata"],
    ].map(([term, value]) => `
      <div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>
    `).join("");
    return;
  }
  const common = [
    ["Tipo contratto", CONTRACT_TYPE[profile.contract_type]],
    ["Società", profile.company],
    ["Numero contratto", profile.contract_number],
  ];
  const economic = profile.contract_type === "lungo_termine"
    ? [
        ["Canone", `${money(profile.monthly_fee)}/mese`],
        ["Franchigia", money(profile.deductible)],
        ["Km inclusi", profile.included_km?.toLocaleString("it-IT")],
        ["Costo km eccedente", money(profile.excess_km_cost)],
      ]
    : profile.contract_type === "breve_termine"
      ? [["Costo giornaliero", `${money(profile.daily_cost)}/giorno`]]
      : profile.contract_type === "leasing"
        ? [
            ["Canone", profile.monthly_fee == null ? null : `${money(profile.monthly_fee)}/mese`],
            ["Franchigia", profile.deductible == null ? null : money(profile.deductible)],
          ]
        : [
            ["Canone", profile.monthly_fee == null ? null : `${money(profile.monthly_fee)}/mese`],
            ["Costo giornaliero", profile.daily_cost == null ? null : `${money(profile.daily_cost)}/giorno`],
            ["Franchigia", profile.deductible == null ? null : money(profile.deductible)],
            ["Km inclusi", profile.included_km?.toLocaleString("it-IT")],
          ];
  const dates = [
    ["Data inizio", profile.starts_on],
    ["Scadenza", profile.expires_on],
    ["Stato contratto", CONTRACT_STATUS[profile.contract_status]],
  ];
  const fields = [...common, ...economic, ...dates].filter(
    ([, value]) => value != null && value !== "",
  );
  target.innerHTML = fields.map(([term, value]) => `
    <div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>
  `).join("");
}


export function renderVehicleDossier(
  payload,
  assetDetail,
  linkedCases = [],
  maintenances = [],
  vehicleDocuments = [],
  franchises = [],
  insurance = [],
) {
  const { asset, kpis, movements } = payload;
  const damageCases = movements.filter((movement) => movement.damage_case_id);
  const openDamageCases = damageCases.filter(
    (movement) => !["chiusa", "annullata"].includes(movement.damage_case_status),
  );
  byId("fleetDossierTitle").textContent = asset.plate || asset.external_identifier;
  byId("fleetDossierModel").textContent = asset.model || "Modello non disponibile";
  byId("fleetDossierStatus").textContent = asset.status === "active" ? "Operativo" : assetValueLabel(asset.status);
  byId("fleetDossierAvailability").textContent = availabilityPresentation(asset.availability).label;
  byId("fleetDossierTerm").textContent = asset.term || "Non classificato";
  byId("fleetDossierLastUse").textContent = dossierTimestamp(kpis.last_use_at);
  byId("fleetDossierOpenDamageCases").textContent = String(openDamageCases.length);
  byId("fleetDossierLastDamageCase").textContent = damageCases[0]?.damage_case_number || "Nessuna";
  byId("fleetDossierOperationalStatus").textContent = availabilityPresentation(
    assetDetail.operational_status || asset.availability,
  ).label;
  byId("fleetDossierOperationalReason").textContent =
    assetDetail.operational_status_reason || "Non registrato";
  byId("fleetDossierOperationalOrigin").textContent =
    assetDetail.operational_status_origin || "Non registrata";
  byId("fleetDossierOperationalActor").textContent =
    assetDetail.operational_status_actor || "Non registrato";
  byId("fleetDossierOperationalUpdated").textContent =
    dossierTimestamp(assetDetail.operational_status_updated_at);
  byId("fleetDossierOperationalCase").textContent =
    assetDetail.operational_status_damage_case_number ||
    (assetDetail.operational_status_damage_case_id
      ? `Pratica #${assetDetail.operational_status_damage_case_id}`
      : "Nessuna");
  renderContractProfile(assetDetail.profile);
  byId("fleetDossierDamageCases").innerHTML = damageCases.length
    ? damageCases.map((movement) => `
        <button type="button" class="fleet-document-item" data-damage-case-link="${movement.damage_case_id}">
          <strong>${escapeHtml(movement.damage_case_number)}</strong>
          <span>${escapeHtml(movement.damage_case_status)} · ${escapeHtml(movement.damage_case_severity)}</span>
        </button>
      `).join("")
    : '<div class="empty-state">Nessuna pratica collegata.</div>';
  byId("fleetDossierMaintenances").innerHTML = maintenances.length
    ? maintenances.map((item) => `
        <button type="button" class="fleet-document-item" data-maintenance-link="${item.id}">
          <strong>${escapeHtml(item.maintenance_number)}</strong>
          <span>${escapeHtml(item.maintenance_type.replaceAll("_", " "))} · ${escapeHtml(item.status.replaceAll("_", " "))}</span>
          <span>${escapeHtml(dossierTimestamp(item.opened_at))}</span>
        </button>
      `).join("")
    : '<div class="empty-state">Nessuna manutenzione registrata.</div>';
  byId("fleetDossierFranchises").innerHTML = franchises.length
    ? franchises.map((item) => `
        <button type="button" class="fleet-document-item" data-franchise-link="${item.id}">
          <strong>${escapeHtml(item.damage_case_number)}</strong>
          <span>${escapeHtml(item.status.replaceAll("_", " "))} · ${item.franchise_expected == null ? "Non prevista" : money(item.franchise_expected)}</span>
          <span>${escapeHtml(item.contract_number || "Contratto non registrato")}</span>
        </button>
      `).join("")
    : '<div class="empty-state">Nessuna valutazione franchigia registrata.</div>';
  byId("fleetDossierInsurance").innerHTML = insurance.length
    ? insurance.map((item) => `
        <button type="button" class="fleet-document-item" data-insurance-link="${item.id}">
          <strong>${escapeHtml(item.company)}</strong>
          <span>${escapeHtml(item.policy_number)} · ${escapeHtml(item.coverage_type.replaceAll("_", " "))}</span>
          <span>Scadenza ${escapeHtml(item.expires_on)} · ${escapeHtml(item.status.replaceAll("_", " "))}</span>
        </button>
      `).join("")
    : '<div class="empty-state">Nessuna polizza assicurativa registrata.</div>';
  mountOperationalDocumentHistory({
    movements,
    list: byId("fleetDossierTimeline"),
    search: byId("fleetOperationalDocumentSearch"),
    filters: byId("fleetOperationalDocumentFilters"),
    count: byId("fleetDossierMovementCount"),
  });
  const expiredDocuments = vehicleDocuments.filter((document) => document.status === "scaduto").length;
  const expiringDocuments = vehicleDocuments.filter((document) => document.status === "in_scadenza").length;
  byId("fleetDossierDocuments").innerHTML = vehicleDocuments.length
    ? `<div class="fleet-document-summary"><strong>${vehicleDocuments.length} documenti</strong><span>${expiredDocuments} scaduti · ${expiringDocuments} in scadenza</span></div>` + vehicleDocuments.map((document) => `
        <article class="fleet-document-item">
          <strong>${escapeHtml(document.title)}</strong>
          <span>${escapeHtml(document.document_type.replaceAll("_", " "))} · ${escapeHtml(document.status.replaceAll("_", " "))}</span>
          <span>${escapeHtml(document.expires_at || "Senza scadenza")} · ${document.has_file ? "File presente" : "File mancante"}</span>
        </article>
      `).join("")
    : '<div class="empty-state">Nessun documento registrato.</div>';
  byId("fleetDossierState").hidden = true;
  byId("fleetDossierContent").hidden = false;
}


export function renderFleetLoading() {
  byId("createAssetBtn").hidden = true;
  byId("fleetExportBtn").disabled = true;
  showDataView("fleetViewState", "fleetDataView", false);
  renderViewState(byId("fleetViewState"), {
    state: "loading",
    title: "Caricamento mezzi",
  });
}


export function renderFleetFailure() {
  byId("createAssetBtn").hidden = true;
  byId("fleetExportBtn").disabled = true;
  showDataView("fleetViewState", "fleetDataView", false);
  renderViewState(byId("fleetViewState"), {
    state: "error",
    title: "Impossibile caricare il parco mezzi",
    description: "Il servizio non ha completato il caricamento. Riprova tra poco.",
    actionLabel: "Riprova",
    action: "retry-fleet",
  });
}


export function renderAssetDetail(asset, events) {
  const detail = byId("fleetAssetDetail");
  byId("openVehicleLibrary").href = `/app/vehicles/?id=${encodeURIComponent(asset.id)}`;
  byId("fleetAssetDetailTitle").textContent = asset.plate || asset.external_identifier;
  byId("fleetAssetPlate").textContent = asset.plate || asset.external_identifier;
  byId("fleetAssetDriver").textContent = fleetDriverLabel(asset, events);
  byId("fleetAssetAvailability").innerHTML = statusBadge(asset);
  byId("fleetAssetNote").textContent = asset.notes || "Nessuna nota";

  byId("fleetAssetDocuments").innerHTML = (asset.documents || []).length
    ? asset.documents.map((document) => `
        <article class="fleet-document-item">
          <strong>${escapeHtml(document.name)}</strong>
          <span>${escapeHtml(documentLabel(document))}</span>
          ${document.reference ? `<span>${escapeHtml(document.reference)}</span>` : ""}
        </article>
      `).join("")
    : '<div class="empty-state">Nessun documento registrato.</div>';

  byId("fleetAssetEvents").innerHTML = events.length
    ? [...events].reverse().map((event) => `
        <article class="fleet-event-item">
          <strong>${escapeHtml(eventLabel(event.event_type))}</strong>
          <span>${escapeHtml(timestamp(event.occurred_at))} · ${escapeHtml(event.actor)}</span>
        </article>
      `).join("")
    : '<div class="empty-state">Nessun evento registrato.</div>';

  if (!detail.open) detail.showModal();
}


export function hideAssetDetail() {
  const detail = byId("fleetAssetDetail");
  if (detail.open) detail.close();
}

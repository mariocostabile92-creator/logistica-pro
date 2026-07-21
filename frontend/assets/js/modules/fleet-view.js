import {
  byId,
  escapeHtml,
  renderViewState,
  showDataView,
} from "../utils/dom.js";
import { assetValueLabel } from "../utils/formatters.js";


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
  if (!value) return "Non disponibile";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
}


export function availabilityPresentation(value) {
  const key = String(value || "").trim().toLowerCase();
  return {
    available: { label: "Disponibile", tone: "available" },
    maintenance: { label: "Officina", tone: "maintenance" },
    unavailable: { label: "Indisponibile", tone: "unavailable" },
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
  return "Non disponibile";
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
  const countAvailability = (value) => assets.filter(
    (asset) => asset.availability === value,
  ).length;
  return {
    total: assets.length,
    available: countAvailability("available"),
    reserve: countAvailability("reserve"),
    maintenance: countAvailability("maintenance"),
    unavailable: countAvailability("unavailable"),
    documentsAttention,
  };
}


function renderFleetSummary(assets) {
  const summary = fleetSummary(assets);
  byId("fleetTotalAssets").textContent = summary.total;
  byId("fleetAvailableAssets").textContent = summary.available;
  byId("fleetUnavailableAssets").textContent = summary.unavailable;
  byId("fleetReserveAssets").textContent = summary.reserve;
  byId("fleetMaintenanceAssets").textContent = summary.maintenance;
  byId("fleetDocumentsAttention").textContent = summary.documentsAttention;
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
  return `
    <tr data-fleet-action="select" data-asset-id="${asset.id}" tabindex="0" aria-label="Apri ${escapeHtml(primaryIdentifier)}">
      <td>
        <strong>${escapeHtml(primaryIdentifier)}</strong>
      </td>
      <td>${statusBadge(asset)}</td>
      <td>${escapeHtml(fleetDriverLabel(asset))}</td>
      <td>${escapeHtml(assetValueLabel(asset.category) || "—")}</td>
      <td>${escapeHtml(timestamp(asset.updated_at))}</td>
    </tr>
  `;
}


function assetCard(asset) {
  const primaryIdentifier = asset.plate || asset.external_identifier;
  return `
    <button type="button" class="fleet-asset-card" data-fleet-action="select" data-asset-id="${asset.id}">
      <span class="fleet-card-heading">
        <strong>${escapeHtml(primaryIdentifier)}</strong>
        ${statusBadge(asset)}
      </span>
      <span class="fleet-card-grid">
        <span><small>Driver associato</small><strong>${escapeHtml(fleetDriverLabel(asset))}</strong></span>
        <span><small>Categoria</small><strong>${escapeHtml(assetValueLabel(asset.category) || "—")}</strong></span>
        <span><small>Ultimo aggiornamento</small><strong>${escapeHtml(timestamp(asset.updated_at))}</strong></span>
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

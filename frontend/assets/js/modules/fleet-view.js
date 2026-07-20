import {
  byId,
  escapeHtml,
  renderViewState,
  showDataView,
} from "../utils/dom.js";


function capabilitiesMarkup(capabilities) {
  if (!capabilities.length) return '<span class="section-note">Nessuna</span>';
  return `
    <div class="asset-token-list">
      ${capabilities.map((item) => `<span class="asset-token">${escapeHtml(item)}</span>`).join("")}
    </div>
  `;
}


function documentLabel(document) {
  const expiry = document.expires_on ? ` · scade ${document.expires_on}` : "";
  return `${document.document_type}${expiry}`;
}


function eventLabel(eventType) {
  const labels = {
    AssetCreated: "Asset creato",
    AssetUpdated: "Asset aggiornato",
    AssetAvailable: "Asset disponibile",
    AssetUnavailable: "Asset non disponibile",
    AssetMaintenanceStarted: "Manutenzione iniziata",
    AssetMaintenanceEnded: "Manutenzione terminata",
    AssetAvailabilityChanged: "Disponibilità modificata",
    AssetAvailabilityObserved: "Disponibilità osservata",
    AssetDocumentAdded: "Documento aggiunto",
  };
  return labels[eventType] || eventType;
}


function timestamp(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
}


function assetRow(asset) {
  return `
    <tr>
      <td><strong>${escapeHtml(asset.external_identifier)}</strong></td>
      <td>${escapeHtml(asset.plate || "—")}</td>
      <td>${escapeHtml(asset.category || "—")}</td>
      <td>${escapeHtml(asset.status)}</td>
      <td><span class="asset-availability">${escapeHtml(asset.availability)}</span></td>
      <td>${capabilitiesMarkup(asset.capabilities)}</td>
      <td>${asset.documents.length}</td>
      <td>${escapeHtml(timestamp(asset.updated_at))}</td>
      <td>
        <div class="fleet-row-actions">
          <button type="button" data-fleet-action="select" data-asset-id="${asset.id}">
            Apri
          </button>
        </div>
      </td>
    </tr>
  `;
}


function assetCard(asset) {
  return `
    <article class="fleet-asset-card">
      <h3>${escapeHtml(asset.external_identifier)}</h3>
      <div class="fleet-card-grid">
        <div><span>Targa</span><strong>${escapeHtml(asset.plate || "—")}</strong></div>
        <div><span>Categoria</span><strong>${escapeHtml(asset.category || "—")}</strong></div>
        <div><span>Stato</span><strong>${escapeHtml(asset.status)}</strong></div>
        <div><span>Disponibilità</span><strong>${escapeHtml(asset.availability)}</strong></div>
        <div><span>Documenti</span><strong>${asset.documents.length}</strong></div>
      </div>
      ${capabilitiesMarkup(asset.capabilities)}
      <div class="fleet-row-actions">
        <button type="button" data-fleet-action="select" data-asset-id="${asset.id}">
          Apri
        </button>
      </div>
    </article>
  `;
}


export function renderAssetList(assets) {
  const tableBody = byId("fleetAssetTableBody");
  const cards = byId("fleetAssetCards");
  if (!assets.length) {
    byId("createAssetBtn").hidden = true;
    showDataView("fleetViewState", "fleetDataView", false);
    renderViewState(byId("fleetViewState"), {
      state: "empty",
      title: "Nessun asset registrato",
      description: "Registra il primo asset per iniziare a gestirne disponibilità e documenti.",
      actionLabel: "Registra asset",
      action: "create-asset",
    });
    return;
  }
  byId("createAssetBtn").hidden = false;
  showDataView("fleetViewState", "fleetDataView", true);
  tableBody.innerHTML = assets.map(assetRow).join("");
  cards.innerHTML = assets.map(assetCard).join("");
}


export function renderFleetLoading() {
  byId("createAssetBtn").hidden = true;
  showDataView("fleetViewState", "fleetDataView", false);
  renderViewState(byId("fleetViewState"), {
    state: "loading",
    title: "Caricamento asset",
  });
}


export function renderFleetFailure() {
  byId("createAssetBtn").hidden = true;
  showDataView("fleetViewState", "fleetDataView", false);
  renderViewState(byId("fleetViewState"), {
    state: "error",
    title: "Impossibile caricare gli asset",
    description: "Il servizio non ha completato il caricamento. Riprova tra poco.",
    actionLabel: "Riprova",
    action: "retry-fleet",
  });
}


export function renderAssetDetail(asset, events) {
  byId("fleetAssetDetail").hidden = false;
  byId("fleetAssetDetailTitle").textContent = asset.external_identifier;

  byId("fleetAssetDocuments").innerHTML = asset.documents.length
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
}


export function hideAssetDetail() {
  byId("fleetAssetDetail").hidden = true;
}

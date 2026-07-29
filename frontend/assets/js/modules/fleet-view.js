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
  if (!value) return "Non registrato";
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
  return `
    <tr data-fleet-action="select" data-asset-id="${asset.id}" tabindex="0" aria-label="Apri scheda mezzo ${escapeHtml(primaryIdentifier)}">
      <td>
        <strong>${escapeHtml(primaryIdentifier)}</strong>
      </td>
      <td>${statusBadge(asset)}</td>
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
  return `
    <button type="button" class="fleet-asset-card" data-fleet-action="select" data-asset-id="${asset.id}" aria-label="Apri scheda mezzo ${escapeHtml(primaryIdentifier)}">
      <span class="fleet-card-heading">
        <strong>${escapeHtml(primaryIdentifier)}</strong>
        ${statusBadge(asset)}
      </span>
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


function operationLabel(value) {
  return value === "check_out" ? "Ritiro" : value === "check_in" ? "Rientro" : "Movimentazione";
}


function dossierMovement(item) {
  const photos = (item.media || []).filter((media) => media.media_type === "image");
  const equipment = (item.equipment || []).map((entry) => `
    <span class="fleet-dossier-chip">
      ${escapeHtml(entry.equipment_label_snapshot)} · ${escapeHtml(assetValueLabel(entry.equipment_status))}
    </span>
  `).join("");
  return `
    <details class="fleet-dossier-movement">
      <summary>
        <span>
          <strong>${escapeHtml(operationLabel(item.operation_type))}</strong>
          <small>${escapeHtml(dossierTimestamp(item.occurred_at))}</small>
        </span>
        <span><small>Km</small><strong>${Number(item.odometer_km).toLocaleString("it-IT")}</strong></span>
        <span><small>Carburante</small><strong>${item.fuel_percentage}%</strong></span>
        <span class="${item.anomaly_present ? "has-anomaly" : ""}">
          <small>Anomalie</small><strong>${item.anomaly_present ? "Presenti" : "Nessuna"}</strong>
        </span>
      </summary>
      <div class="fleet-dossier-movement-body">
        <dl>
          <div><dt>Driver dichiarato</dt><dd>${escapeHtml(item.declared_driver_identifier || "—")}</dd></div>
          <div><dt>Pulizia</dt><dd>${escapeHtml(assetValueLabel(item.cleanliness_status) || "—")}</dd></div>
          <div><dt>Anomalia</dt><dd>${escapeHtml(item.anomaly_description || "Nessuna")}</dd></div>
          <div><dt>Nota operativa</dt><dd>${escapeHtml(item.operational_note || "—")}</dd></div>
        </dl>
        <div><h4>Dotazioni</h4><div class="fleet-dossier-chips">${equipment || "Non registrate"}</div></div>
        <div>
          <h4>Foto</h4>
          ${photos.length
            ? `<div class="fleet-dossier-media">${photos.map((media) => `
                <a href="${escapeHtml(media.url)}" target="_blank" rel="noreferrer">
                  <img src="${escapeHtml(media.url)}" alt="Foto movimentazione" loading="lazy" />
                </a>
              `).join("")}</div>`
            : '<p class="section-note">Nessuna foto allegata.</p>'}
        </div>
        <div><h4>Video</h4><div class="fleet-video-placeholder">Video non disponibili in questa versione</div></div>
      </div>
    </details>
  `;
}


export function renderVehicleDossier(payload, assetDetail) {
  const { asset, kpis, movements } = payload;
  byId("fleetDossierTitle").textContent = asset.plate || asset.external_identifier;
  byId("fleetDossierModel").textContent = asset.model || "Modello non disponibile";
  byId("fleetDossierStatus").textContent = asset.status === "active" ? "Operativo" : assetValueLabel(asset.status);
  byId("fleetDossierAvailability").textContent = availabilityPresentation(asset.availability).label;
  byId("fleetDossierTerm").textContent = asset.term || "Non classificato";
  byId("fleetDossierLastUse").textContent = dossierTimestamp(kpis.last_use_at);
  byId("fleetDossierMovementCount").textContent = `${movements.length} ${movements.length === 1 ? "evento" : "eventi"}`;
  byId("fleetDossierTimeline").innerHTML = movements.length
    ? movements.map(dossierMovement).join("")
    : '<div class="empty-state">Nessuna movimentazione registrata.</div>';
  byId("fleetDossierDocuments").innerHTML = (assetDetail.documents || []).length
    ? assetDetail.documents.map((document) => `
        <article class="fleet-document-item">
          <strong>${escapeHtml(document.name)}</strong>
          <span>${escapeHtml(documentLabel(document))}</span>
          ${document.reference ? `<span>${escapeHtml(document.reference)}</span>` : ""}
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

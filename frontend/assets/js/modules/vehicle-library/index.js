import { getFleetAsset, getFleetVehicleHistory, getHealth } from "../../api.js";
import { escapeHtml } from "../../utils/dom.js";
import { mountOperationalDocumentHistory } from "./operational-documents.js";
import { openOperationalStatusControl } from "../operational-status-control.js";
import { mountAttachments } from "../attachments/component.js";

const byId = (id) => document.getElementById(id);
let currentAsset = null;

function label(value, labels) {
  return labels[value] || value || "Non registrato";
}

function fullDate(value) {
  if (!value) return "Non registrato";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
}

const AVAILABILITY = Object.freeze({
  disponibile: { label: "Disponibile", tone: "available" },
  available: { label: "Disponibile", tone: "available" },
  disponibile_con_limitazioni: {
    label: "Disponibile con limitazioni",
    tone: "reserve",
  },
  reserve: { label: "Disponibile con limitazioni", tone: "reserve" },
  indisponibile: { label: "Indisponibile", tone: "unavailable" },
  unavailable: { label: "Indisponibile", tone: "unavailable" },
  in_manutenzione: { label: "In manutenzione", tone: "maintenance" },
  maintenance: { label: "In manutenzione", tone: "maintenance" },
  in_officina: { label: "In officina", tone: "maintenance" },
  workshop: { label: "In officina", tone: "maintenance" },
});

function availabilityPresentation(value) {
  const originalValue = String(value || "").trim();
  return AVAILABILITY[originalValue.toLowerCase()] || {
    label: "Non classificato",
    tone: "unknown",
    originalValue,
  };
}

export function availability(value) {
  return availabilityPresentation(value).label;
}

function operation(value) {
  return label(value, { check_out: "Ritiro", check_in: "Rientro" });
}

function renderContractProfile(profile) {
  const target = byId("vehicleContractProfile");
  if (!profile) {
    target.innerHTML = "<div><dt>Profilo</dt><dd>Non ancora configurato</dd></div>";
    return;
  }
  const type = {
    lungo_termine: "Lungo termine",
    breve_termine: "Breve termine",
    proprieta: "Proprietà",
    leasing: "Leasing",
    altro: "Altro",
  }[profile.contract_type];
  const values = [
    ["Tipo contratto", type],
    ["Società", profile.company || profile.owner_company || "Non registrata"],
    ["Numero contratto", profile.contract_number || "Non registrato"],
    ["Stato contratto", {
      attivo: "Attivo",
      in_scadenza: "In scadenza",
      scaduto: "Scaduto",
    }[profile.contract_status]],
  ];
  target.innerHTML = values.map(([term, value]) => `
    <div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>
  `).join("");
}

async function render(payload, assetDetail) {
  const { asset, kpis, movements } = payload;
  currentAsset = asset;
  byId("vehiclePlate").textContent = asset.plate || asset.external_identifier;
  byId("vehicleModel").textContent = asset.model || "Modello non disponibile";
  byId("vehicleStatus").textContent = label(asset.status, {
    active: "Operativo",
    inactive: "Non operativo",
  });
  const operationalStatus = availabilityPresentation(asset.availability);
  byId("vehicleAvailability").textContent = operationalStatus.label;
  byId("vehicleAvailability").className =
    `fleet-status-badge fleet-status-${operationalStatus.tone}`;
  byId("vehicleTerm").textContent = asset.term || "Non classificato";
  byId("vehicleOperationalReason").textContent =
    assetDetail.operational_status_reason || "Non registrato";
  byId("vehicleOperationalOrigin").textContent =
    assetDetail.operational_status_origin || "Non registrata";
  byId("vehicleOperationalActor").textContent =
    assetDetail.operational_status_actor || "Non registrato";
  byId("vehicleOperationalUpdated").textContent =
    fullDate(assetDetail.operational_status_updated_at);
  byId("vehicleOperationalCase").textContent =
    assetDetail.operational_status_damage_case_number ||
    (assetDetail.operational_status_damage_case_id
      ? `Pratica #${assetDetail.operational_status_damage_case_id}`
      : "Nessuna");
  renderContractProfile(assetDetail.profile);
  byId("currentKm").textContent = kpis.current_odometer_km == null
    ? "Non registrati"
    : `${Number(kpis.current_odometer_km).toLocaleString("it-IT")} km`;
  byId("lastUse").textContent = fullDate(kpis.last_use_at);
  byId("daysStopped").textContent = kpis.days_stopped == null
    ? "Non calcolabile"
    : `${kpis.days_stopped} gg`;
  byId("lastDriver").textContent = kpis.last_declared_driver || "Non registrato";
  byId("lastMovement").textContent = operation(kpis.last_movement);
  mountOperationalDocumentHistory({
    movements,
    list: byId("operationalDocumentList"),
    search: byId("operationalDocumentSearch"),
    filters: byId("operationalDocumentFilters"),
    count: byId("operationalDocumentCount"),
  });
  document.title = `${asset.plate || asset.external_identifier} · Vehicle Library`;
  byId("vehicleState").hidden = true;
  byId("vehicleContent").hidden = false;
  await mountAttachments(byId("vehicleAttachments"), {
    entityType: "vehicle", entityId: asset.id, aggregateVehicle: true,
    title: "Allegati del mezzo",
  });
}

async function checkHealth() {
  const badge = byId("healthStatus");
  try {
    await getHealth();
    badge.textContent = "Backend online";
    badge.className = "status-pill ok";
  } catch {
    badge.textContent = "Backend non raggiungibile";
  }
}

async function loadVehicle() {
  const assetId = Number(new URLSearchParams(location.search).get("id"));
  if (!Number.isInteger(assetId) || assetId < 1) {
    throw new Error("Seleziona un mezzo dal Fleet Registry.");
  }
  const [history, asset] = await Promise.all([
    getFleetVehicleHistory(assetId),
    getFleetAsset(assetId),
  ]);
  await render(history, asset);
}

if (typeof document !== "undefined") {
  byId("vehicleChangeStatus").addEventListener("click", () => {
    openOperationalStatusControl({
      asset: currentAsset,
      origin: "vehicle_library",
      onChanged: loadVehicle,
    });
  });
  checkHealth();
  loadVehicle().catch((error) => {
    byId("vehicleState").innerHTML = `
      <div>
        <strong>${escapeHtml(error.message)}</strong>
        <p><a href="/app/?view=fleet">Torna al Fleet Registry</a></p>
      </div>
    `;
  });
}

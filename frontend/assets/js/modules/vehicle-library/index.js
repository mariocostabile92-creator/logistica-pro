import { getFleetVehicleHistory, getHealth } from "../../api.js";
import { escapeHtml } from "../../utils/dom.js";
import { mountOperationalDocumentHistory } from "./operational-documents.js";

const byId = (id) => document.getElementById(id);

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

function availability(value) {
  return label(value, {
    available: "Disponibile",
    unavailable: "Indisponibile",
    maintenance: "Officina",
    reserve: "Riserva",
  });
}

function operation(value) {
  return label(value, { check_out: "Ritiro", check_in: "Rientro" });
}

function render(payload) {
  const { asset, kpis, movements } = payload;
  byId("vehiclePlate").textContent = asset.plate || asset.external_identifier;
  byId("vehicleModel").textContent = asset.model || "Modello non disponibile";
  byId("vehicleStatus").textContent = label(asset.status, {
    active: "Operativo",
    inactive: "Non operativo",
  });
  byId("vehicleAvailability").textContent = availability(asset.availability);
  byId("vehicleTerm").textContent = asset.term || "Non classificato";
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
  render(await getFleetVehicleHistory(assetId));
}

checkHealth();
loadVehicle().catch((error) => {
  byId("vehicleState").innerHTML = `
    <div>
      <strong>${escapeHtml(error.message)}</strong>
      <p><a href="/app/?view=fleet">Torna al Fleet Registry</a></p>
    </div>
  `;
});

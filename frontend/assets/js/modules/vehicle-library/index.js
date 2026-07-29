import { getHealth } from "../../api.js";
import { escapeHtml } from "../../utils/dom.js";


const API_BASE = globalThis.OPERATIONS_API_URL || "";
const byId = (id) => document.getElementById(id);


function label(value, labels) {
  return labels[value] || value || "Non registrato";
}


function dateParts(value) {
  if (!value) return { date: "—", time: "" };
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return { date: value, time: "" };
  return {
    date: parsed.toLocaleDateString("it-IT"),
    time: parsed.toLocaleTimeString("it-IT", {
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}


function fullDate(value) {
  if (!value) return "Non registrato";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT", {
        dateStyle: "medium",
        timeStyle: "short",
      });
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


function movementCard(item) {
  const occurred = dateParts(item.occurred_at);
  const equipment = item.equipment.length
    ? item.equipment.map((entry) => `
        <span class="equipment-chip">
          ${escapeHtml(entry.equipment_label_snapshot)}:
          ${escapeHtml(label(entry.equipment_status, {
            present: "presente",
            absent: "assente",
            damaged: "danneggiato",
          }))}
        </span>
      `).join("")
    : '<span class="equipment-chip">Nessuna dotazione registrata</span>';
  const photos = item.media
    .filter((media) => media.media_type === "image")
    .map((media) => `
      <a href="${escapeHtml(media.url)}" target="_blank" rel="noreferrer">
        <img src="${escapeHtml(media.url)}" alt="Foto della movimentazione" loading="lazy" />
      </a>
    `).join("");
  return `
    <details class="movement-card">
      <summary>
        <span class="movement-time">
          <strong>${escapeHtml(occurred.date)}</strong>
          <span>${escapeHtml(occurred.time)}</span>
        </span>
        <strong class="movement-kind">
          ${escapeHtml(operation(item.operation_type))}
          <small>${escapeHtml(item.declared_driver_identifier)}</small>
        </strong>
        <span class="movement-metric"><span>Km</span><strong>${item.odometer_km.toLocaleString("it-IT")}</strong></span>
        <span class="movement-metric movement-fuel"><span>Carburante</span><strong>${item.fuel_percentage}%</strong></span>
        <span class="movement-metric"><span>Anomalie</span><strong>${item.anomaly_present ? "Sì" : "No"}</strong></span>
      </summary>
      <div class="movement-details">
        <div class="movement-detail-grid">
          <div><span>Data e ora</span><strong>${escapeHtml(fullDate(item.occurred_at))}</strong></div>
          <div><span>Operazione</span><strong>${escapeHtml(operation(item.operation_type))}</strong></div>
          <div><span>Driver dichiarato</span><strong>${escapeHtml(item.declared_driver_identifier)}</strong></div>
          <div><span>Chilometri</span><strong>${item.odometer_km.toLocaleString("it-IT")} km</strong></div>
          <div><span>Carburante</span><strong>${item.fuel_percentage}%</strong></div>
          <div><span>Pulizia</span><strong>${escapeHtml(label(item.cleanliness_status, {
            compliant: "Conforme",
            non_compliant: "Non conforme",
            verify: "Da verificare",
          }))}</strong></div>
          <div><span>Anomalie</span><strong>${item.anomaly_present ? "Presenti" : "Nessuna"}</strong></div>
          <div><span>Dettaglio anomalia</span><strong>${escapeHtml(item.anomaly_description || "—")}</strong></div>
          <div><span>Nota operativa</span><strong>${escapeHtml(item.operational_note || "—")}</strong></div>
        </div>
        <div class="movement-equipment">
          <h4>Dotazioni</h4>
          <div class="equipment-chips">${equipment}</div>
        </div>
        <div class="movement-media">
          <h4>Foto</h4>
          ${photos
            ? `<div class="movement-media-grid">${photos}</div>`
            : '<p class="vehicle-empty">Nessuna foto allegata.</p>'}
        </div>
        <div class="movement-media">
          <h4>Video</h4>
          <div class="video-placeholder">Video non disponibili in questa versione</div>
        </div>
      </div>
    </details>
  `;
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
  byId("movementCount").textContent = `${movements.length} ${movements.length === 1 ? "evento" : "eventi"}`;
  byId("movementTimeline").innerHTML = movements.length
    ? movements.map(movementCard).join("")
    : '<div class="vehicle-empty">Nessuna movimentazione registrata nel Driver Journal.</div>';
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
  const response = await fetch(
    `${API_BASE}/api/plugins/fleet/v1/journal/vehicles/${assetId}/history`,
  );
  if (!response.ok) throw new Error("Cartella mezzo non disponibile.");
  render(await response.json());
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

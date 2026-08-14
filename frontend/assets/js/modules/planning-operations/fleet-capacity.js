import { escapeHtml } from "../../utils/dom.js";


function metric(value) {
  return value === null || value === undefined ? "—" : String(value);
}

const BUCKET_LABELS = {
  NEXT_DAY: "Next Day",
  SAME_DAY_A: "Same Day A",
  SAME_DAY_B_C: "Same Day B-C",
};


export function fleetCapacityTone(snapshot) {
  if (!snapshot || snapshot.vehicle_need === null) return "unknown";
  if (snapshot.vehicle_need_status === "PARTIAL") return "partial";
  return snapshot.margin < 0 ? "shortage" : "sufficient";
}


export function fleetCapacityMessage(snapshot) {
  if (!snapshot || snapshot.vehicle_need === null) {
    return "Fabbisogno mezzi da configurare";
  }
  if (snapshot.vehicle_need_status === "PARTIAL") {
    return `Almeno ${snapshot.vehicle_need} mezzi necessari`;
  }
  if (snapshot.margin < 0) {
    return `Mancano ${Math.abs(snapshot.margin)} mezzi`;
  }
  return "Capacità Fleet sufficiente";
}


export function fleetCapacityDetail(snapshot) {
  if (!snapshot || snapshot.vehicle_need === null) {
    return "Nessun bucket possiede ancora un forecast effettivo.";
  }
  if (snapshot.vehicle_need_status === "PARTIAL") {
    const missing = (snapshot.missing_requirement_buckets || [])
      .map((bucket) => BUCKET_LABELS[bucket] || bucket)
      .join(", ");
    const margin = snapshot.margin === null
      ? ""
      : ` Margine sul fabbisogno noto: ${snapshot.margin > 0 ? "+" : ""}${snapshot.margin} mezzi.`;
    return `${missing || "Un bucket"} ancora da configurare.${margin}`;
  }
  if (snapshot.margin < 0) {
    return "Il requirement operativo +10% supera i mezzi attualmente disponibili.";
  }
  return `+${snapshot.margin} mezzi di margine sul requirement operativo +10%.`;
}


export function fleetCapacityDate(value) {
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? String(value || "")
    : parsed.toLocaleDateString("it-IT", { day: "numeric", month: "long" });
}


function routeAssignments(snapshot) {
  if (!snapshot?.route_assignments_available) {
    return `<div class="planning-fleet-assignments is-waiting">
      <span>Assegnazioni mezzi alle rotte</span>
      <strong>In attesa delle rotte definitive</strong>
    </div>`;
  }
  return `<div class="planning-fleet-assignments">
    <span>Assegnazioni mezzi alle rotte</span>
    <strong>${metric(snapshot.assigned_vehicles)} assegnati</strong>
    <small>${metric(snapshot.routes_without_vehicle)} rotte senza mezzo</small>
  </div>`;
}


export function renderFleetCapacity(snapshot) {
  if (!snapshot) {
    return `<section class="planning-ops-panel planning-fleet-capacity" data-fleet-capacity-state="unavailable">
      <header><div><p class="eyebrow">Fleet input</p><h3>Capacità flotta</h3></div><button type="button" class="secondary" data-open-fleet>Apri Fleet</button></header>
      <p class="planning-ops-empty">Capacità Fleet non disponibile.</p>
    </section>`;
  }
  const tone = fleetCapacityTone(snapshot);
  const stationNote = snapshot.requested_station && !snapshot.station_scope_applied
    ? `Fleet non associa ancora i mezzi alla station ${escapeHtml(snapshot.requested_station)}: il conteggio copre l’intera organizzazione.`
    : "Conteggio dell’intero parco dell’organizzazione.";
  return `<section class="planning-ops-panel planning-fleet-capacity" data-fleet-capacity-state="${tone}">
    <header><div><p class="eyebrow">Fleet input · ${escapeHtml(fleetCapacityDate(snapshot.operational_date))}</p><h3>Capacità flotta</h3></div><button type="button" class="secondary" data-open-fleet>Apri Fleet</button></header>
    <div class="planning-fleet-metrics" aria-label="Capacità Fleet">
      <article><strong>${snapshot.total_vehicles}</strong><span>Totale mezzi</span></article>
      <article class="is-positive"><strong>${snapshot.available_vehicles}</strong><span>Disponibili</span></article>
      <article><strong>${snapshot.unavailable_vehicles}</strong><span>Indisponibili</span></article>
      <article><strong>${snapshot.maintenance_vehicles}</strong><span>Manutenzione</span></article>
      <article><strong>${snapshot.blocked_vehicles}</strong><span>Bloccati / officina</span></article>
      <article><strong>${snapshot.unknown_vehicles}</strong><span>Da classificare</span></article>
      <article><strong>${metric(snapshot.vehicle_need)}</strong><span>Fabbisogno mezzi</span></article>
      <article><strong>${snapshot.margin === null ? "—" : snapshot.margin > 0 ? `+${snapshot.margin}` : snapshot.margin}</strong><span>Margine</span></article>
    </div>
    <div class="planning-fleet-capacity-message" role="status">
      ${snapshot.vehicle_need_status === "PARTIAL" ? '<small>Fabbisogno parziale</small>' : ""}
      <strong>${escapeHtml(fleetCapacityMessage(snapshot))}</strong>
      <span>${escapeHtml(fleetCapacityDetail(snapshot))}</span>
    </div>
    ${routeAssignments(snapshot)}
    <p class="planning-fleet-source">${stationNote} Lo stato è quello operativo corrente: Fleet non conserva ancora una disponibilità storica per data.</p>
  </section>`;
}

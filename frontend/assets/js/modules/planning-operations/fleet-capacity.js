import { escapeHtml } from "../../utils/dom.js";


function metric(value) {
  return value === null || value === undefined ? "—" : String(value);
}


export function fleetCapacityTone(snapshot) {
  if (!snapshot || snapshot.vehicle_need === null) return "unknown";
  return snapshot.margin < 0 ? "shortage" : "sufficient";
}


export function fleetCapacityMessage(snapshot) {
  if (!snapshot || snapshot.vehicle_need === null) {
    return "Fabbisogno mezzi non ancora determinabile";
  }
  if (snapshot.margin < 0) {
    return `Mancano ${Math.abs(snapshot.margin)} mezzi`;
  }
  return "Capacità Fleet sufficiente";
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
    <div class="planning-fleet-capacity-message" role="status"><strong>${escapeHtml(fleetCapacityMessage(snapshot))}</strong><span>Il fabbisogno sarà valorizzato solo quando esisterà una regola operativa autorevole.</span></div>
    ${routeAssignments(snapshot)}
    <p class="planning-fleet-source">${stationNote} Lo stato è quello operativo corrente: Fleet non conserva ancora una disponibilità storica per data.</p>
  </section>`;
}

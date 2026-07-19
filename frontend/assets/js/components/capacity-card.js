import { escapeHtml } from "../utils/dom.js";


export function capacityCard(capacity) {
  const suggestions = capacity.cross_station_suggestions || [];
  return `
    <article class="capacity-card ${escapeHtml(capacity.readiness)}">
      <div class="capacity-card-header">
        <h4>${escapeHtml(capacity.station)}</h4>
        <span class="planning-status ${escapeHtml(capacity.readiness)}">${escapeHtml(capacity.readiness)}</span>
      </div>
      <div class="capacity-values">
        <div><span>Rotte</span><strong>${capacity.routes_total}</strong></div>
        <div><span>Driver</span><strong>${capacity.drivers_available}</strong></div>
        <div><span>Operativi</span><strong>${capacity.operational_vehicles}</strong></div>
        <div><span>Margine</span><strong>${capacity.operational_margin > 0 ? "+" : ""}${capacity.operational_margin}</strong></div>
        <div><span>Riserva</span><strong>${capacity.safe_reserve_vehicles}</strong></div>
        <div><span>Bloccati</span><strong>${capacity.blocked_vehicles}</strong></div>
      </div>
      ${capacity.issues.length ? `<p class="capacity-issues">${escapeHtml(capacity.issues.join(" "))}</p>` : ""}
      ${suggestions.map((item) => `
        <p class="cross-station-note">Suggerimento: ${escapeHtml(item.plate)} da ${escapeHtml(item.from_station)} a ${escapeHtml(item.to_station)}. Non applicato.</p>
      `).join("")}
    </article>
  `;
}

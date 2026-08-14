import { escapeHtml } from "../../utils/dom.js";


export function availabilityCard(driver) {
  const reserve = driver.is_reserve
    ? '<span class="workforce-reserve-badge">Riserva</span>'
    : "";
  const cycle = ({
    NEXT_DAY: "Next Day",
    SAME_DAY: "Same Day",
    NOT_SET: "Non impostato",
  })[driver.operational_cycle] || "Non impostato";
  return `<article class="workforce-driver-readiness" data-tone="${escapeHtml(driver.callability_tone)}">
    <div class="workforce-driver-identity"><strong>${escapeHtml(driver.display_name)}</strong><span>${escapeHtml(driver.role || "Ruolo non indicato")}</span></div>
    <div><span>Station</span><strong>${escapeHtml(driver.station || "Non indicata")}</strong></div>
    <div><span>Contratto</span><strong>${escapeHtml(driver.contract || "Non indicato")}</strong></div>
    <div><span>Ciclo</span><strong class="workforce-cycle-badge" data-cycle="${escapeHtml(driver.operational_cycle || "NOT_SET")}">${escapeHtml(cycle)}</strong></div>
    <div><span>Disponibilita</span><strong>${escapeHtml(driver.availability_label)}</strong></div>
    <div class="workforce-driver-state-compact"><span class="workforce-readiness-badge">${escapeHtml(driver.callability_label)}</span>${reserve}<strong>${escapeHtml(driver.callability_reason)}</strong></div>
    <button type="button" class="quiet workforce-driver-detail-button" data-workforce-driver-detail="${driver.workforce_member_id}">Vedi / Modifica</button>
  </article>`;
}

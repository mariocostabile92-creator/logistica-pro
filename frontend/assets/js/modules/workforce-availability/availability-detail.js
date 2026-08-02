import { escapeHtml } from "../../utils/dom.js";
import { consecutivityDetail } from "../workforce-consecutivity/consecutivity-detail.js";

function timestamp(value) {
  if (!value) return "Non disponibile";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
}

export function createAvailabilityDetail() {
  const dialog = document.getElementById("workforceAvailabilityDetail");
  document.getElementById("workforceAvailabilityDetailClose")?.addEventListener("click", () => dialog.close());
  return {
    open(driver) {
      document.getElementById("workforceAvailabilityDetailTitle").textContent = driver.display_name;
      document.getElementById("workforceAvailabilityDetailBody").innerHTML = `
        <dl class="workforce-availability-detail-grid">
          <div><dt>Disponibilita</dt><dd>${escapeHtml(driver.availability_label)}</dd></div>
          <div><dt>Stato</dt><dd>${escapeHtml(driver.callability_label)}</dd></div>
          <div><dt>Motivo</dt><dd>${escapeHtml(driver.callability_reason)}</dd></div>
          <div><dt>Ultimo aggiornamento</dt><dd>${escapeHtml(timestamp(driver.last_updated_at))}</dd></div>
        </dl>
        <section><h4>Limitazioni</h4><p>${escapeHtml(driver.limitations?.join(" · ") || "Nessuna limitazione.")}</p></section>
        <section><h4>Storico stato</h4><div class="workforce-availability-history">${driver.status_history?.length
          ? driver.status_history.map((item) => `<article><strong>${escapeHtml(item.date)} · ${escapeHtml(item.callability_label)}</strong><span>${escapeHtml(item.reason)}</span><small>${escapeHtml(timestamp(item.updated_at))}</small></article>`).join("")
          : "<p>Nessuno storico disponibile.</p>"}</div></section>
        ${consecutivityDetail(driver)}`;
      dialog.showModal();
    },
  };
}

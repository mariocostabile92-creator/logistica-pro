import { escapeHtml } from "../utils/dom.js";


const ACCESS_LABELS = Object.freeze({
  NOT_OPENED: "Non visualizzato",
  OPENED: "Visualizzato",
  ACKNOWLEDGED: "Presa visione",
});


function dateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}


export function filterDistributionRecipients(recipients, filter = "", search = "") {
  const query = search.trim().toLocaleLowerCase("it-IT");
  return recipients.filter((recipient) => (
    (!filter || recipient.access_status === filter)
    && (!query || recipient.display_name.toLocaleLowerCase("it-IT").includes(query))
  ));
}


export function renderDistributionSummary(element, summary) {
  const values = [
    ["Destinatari", summary.recipients_total],
    ["Pronti", summary.ready],
    ["Visualizzati", summary.opened],
    ["Presa visione", summary.acknowledged],
    ["Non visualizzati", summary.not_opened],
  ];
  element.innerHTML = values.map(([label, value]) => `
    <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value ?? 0))}</dd></div>
  `).join("");
}


export function renderDistributionRecipients(element, recipients) {
  if (!recipients.length) {
    element.innerHTML = '<p class="driver-shift-distribution-empty">Nessun destinatario corrisponde ai filtri.</p>';
    return;
  }
  element.innerHTML = recipients.map((recipient) => `
    <article class="driver-shift-recipient" data-recipient-id="${recipient.id}">
      <div class="driver-shift-recipient-main">
        <strong>${escapeHtml(recipient.display_name)}</strong>
        <span>${recipient.shift_days_count} ${recipient.shift_days_count === 1 ? "giornata" : "giornate"}</span>
      </div>
      <div class="driver-shift-recipient-state">
        <span data-access-status="${escapeHtml(recipient.access_revoked ? "REVOKED" : recipient.access_status)}">${escapeHtml(recipient.access_revoked ? "Revocato" : (ACCESS_LABELS[recipient.access_status] || "Non disponibile"))}</span>
        ${recipient.acknowledged_at ? `<small>${escapeHtml(dateTime(recipient.acknowledged_at))}</small>` : ""}
      </div>
      <div class="driver-shift-recipient-actions">
        <button type="button" data-copy-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Copia link</button>
        <button type="button" class="secondary" data-regenerate-shift-link="${recipient.id}">Rigenera</button>
        <button type="button" class="quiet" data-revoke-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Revoca</button>
      </div>
    </article>
  `).join("");
}

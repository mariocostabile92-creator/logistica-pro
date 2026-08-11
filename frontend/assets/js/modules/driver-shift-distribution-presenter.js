import { escapeHtml } from "../utils/dom.js";
import { credentialLabel } from "./driver-shift-credentials-presenter.js?v=1";


const ACCESS_LABELS = Object.freeze({
  NOT_OPENED: "Non visualizzato",
  OPENED: "Visualizzato",
  ACKNOWLEDGED: "Presa visione",
});

const READINESS_LABELS = Object.freeze({
  READY: "Pronto",
  MISSING_CONTACT: "Contatto mancante",
  INVALID_CONTACT: "Contatto non valido",
  EXCLUDED: "Escluso",
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
    (!filter
      || (filter === "READY" && recipient.readiness === "READY")
      || (filter === "EXCEPTIONS" && ["MISSING_CONTACT", "INVALID_CONTACT", "EXCLUDED"].includes(recipient.readiness))
      || recipient.access_status === filter)
    && (!query || recipient.display_name.toLocaleLowerCase("it-IT").includes(query))
  ));
}


export function renderDistributionSummary(element, summary, selectedCount = 0) {
  const values = [
    ["Destinatari", summary.recipients_total],
    ["Pronti", summary.contact_ready],
    ["Senza contatto", summary.missing_contact],
    ["Non validi", summary.invalid_contact],
    ["Selezionati", selectedCount],
    ["Visualizzati", summary.opened],
    ["Presa visione", summary.acknowledged],
    ["Non visualizzati", summary.not_opened],
  ];
  element.innerHTML = values.map(([label, value]) => `
    <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value ?? 0))}</dd></div>
  `).join("");
}


export function renderDistributionRecipients(
  element, recipients, selectedIds = new Set(), credentialStatuses = new Map(),
) {
  if (!recipients.length) {
    element.innerHTML = '<p class="driver-shift-distribution-empty">Nessun destinatario corrisponde ai filtri.</p>';
    return;
  }
  element.innerHTML = recipients.map((recipient) => {
    const credentialStatus = credentialStatuses.get(Number(recipient.workforce_member_id)) || "MISSING";
    return `
    <article class="driver-shift-recipient" data-recipient-id="${recipient.id}">
      <label class="driver-shift-recipient-select">
        <input type="checkbox" data-select-shift-recipient="${recipient.id}"
          ${selectedIds.has(recipient.id) ? "checked" : ""}
          ${recipient.readiness !== "READY" || recipient.access_revoked ? "disabled" : ""} />
        <span class="sr-only">Seleziona ${escapeHtml(recipient.display_name)}</span>
      </label>
      <div class="driver-shift-recipient-main">
        <strong>${escapeHtml(recipient.display_name)}</strong>
        <span>${recipient.shift_days_count} ${recipient.shift_days_count === 1 ? "giornata" : "giornate"}</span>
        <small>${escapeHtml((recipient.available_channels || []).join(" · ") || "Nessun canale disponibile")}</small>
        <span class="driver-shift-credential-state" data-credential-status="${escapeHtml(credentialStatus)}">${escapeHtml(credentialLabel(credentialStatus))}</span>
        ${credentialStatus !== "MISSING" ? `
          <div class="driver-shift-credential-actions">
            ${credentialStatus !== "REVOKED" ? `<button type="button" class="secondary" data-reset-driver-credential="${recipient.workforce_member_id}">Reimposta PIN</button>` : ""}
            ${credentialStatus !== "REVOKED" ? `<button type="button" class="quiet" data-revoke-driver-credential="${recipient.workforce_member_id}">Revoca accesso</button>` : ""}
          </div>
        ` : ""}
      </div>
      <div class="driver-shift-recipient-state">
        <span data-readiness="${escapeHtml(recipient.readiness)}">${escapeHtml(READINESS_LABELS[recipient.readiness] || "Da verificare")}</span>
        <span data-access-status="${escapeHtml(recipient.access_revoked ? "REVOKED" : recipient.access_status)}">${escapeHtml(recipient.access_revoked ? "Revocato" : (ACCESS_LABELS[recipient.access_status] || "Non disponibile"))}</span>
        ${recipient.acknowledged_at ? `<small>${escapeHtml(dateTime(recipient.acknowledged_at))}</small>` : ""}
      </div>
      <div class="driver-shift-recipient-actions">
        <button type="button" data-copy-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Copia link</button>
        <button type="button" class="secondary" data-regenerate-shift-link="${recipient.id}">Rigenera</button>
        <button type="button" class="quiet" data-revoke-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Revoca</button>
      </div>
    </article>
  `;
  }).join("");
}

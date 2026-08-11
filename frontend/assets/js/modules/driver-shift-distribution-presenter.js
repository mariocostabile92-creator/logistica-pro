import { escapeHtml } from "../utils/dom.js";
import { credentialLabel } from "./driver-shift-credentials-presenter.js?v=2";


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


export function filterDistributionRecipients(
  recipients, filter = "", search = "", credentialStatuses = new Map(),
) {
  const query = search.trim().toLocaleLowerCase("it-IT");
  return recipients.filter((recipient) => {
    const credentialStatus = credentialStatuses.get(Number(recipient.workforce_member_id)) || "MISSING";
    return (
      (!filter
        || (filter === "ACCESS_MISSING" && credentialStatus !== "ACTIVE")
        || recipient.access_status === filter)
      && (!query || recipient.display_name.toLocaleLowerCase("it-IT").includes(query))
    );
  });
}


export function renderDistributionSummary(element, summary, credentialSummary = {}) {
  const total = Number(credentialSummary.recipients_total ?? summary.recipients_total ?? 0);
  const ready = Number(credentialSummary.credentials_ready ?? 0);
  const values = [
    ["Destinatari settimana", total],
    ["Accessi pronti", ready],
    ["Accessi da preparare", Math.max(0, total - ready)],
    ["Visualizzati", summary.opened],
    ["Presa visione", summary.acknowledged],
    ["Non visualizzati", summary.not_opened],
  ];
  element.innerHTML = values.map(([label, value]) => `
    <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value ?? 0))}</dd></div>
  `).join("");
}


export function renderDistributionRecipients(
  element, recipients, credentialStatusesOrLegacySelection = new Map(), legacyCredentialStatuses = null,
) {
  const credentialStatuses = legacyCredentialStatuses
    || (typeof credentialStatusesOrLegacySelection?.get === "function"
      ? credentialStatusesOrLegacySelection : new Map());
  if (!recipients.length) {
    element.innerHTML = '<p class="driver-shift-distribution-empty">Nessun destinatario corrisponde ai filtri.</p>';
    return;
  }
  element.innerHTML = recipients.map((recipient) => {
    const credentialStatus = credentialStatuses.get(Number(recipient.workforce_member_id)) || "MISSING";
    const accessStatus = recipient.access_revoked ? "REVOKED" : recipient.access_status;
    const accessLabel = credentialStatus === "REVOKED" ? "Accesso revocato" : credentialLabel(credentialStatus);
    return `
    <article class="driver-shift-recipient" data-recipient-id="${recipient.id}">
      <div class="driver-shift-recipient-main">
        <strong>${escapeHtml(recipient.display_name)}</strong>
        <span>${recipient.shift_days_count} ${recipient.shift_days_count === 1 ? "giornata" : "giornate"}</span>
      </div>
      <div class="driver-shift-recipient-state">
        <span class="driver-shift-credential-state" data-credential-status="${escapeHtml(credentialStatus)}">${escapeHtml(accessLabel)}</span>
        <span data-access-status="${escapeHtml(accessStatus)}">${escapeHtml(recipient.access_revoked ? "Accesso revocato" : (ACCESS_LABELS[recipient.access_status] || "Non visualizzato"))}</span>
        ${recipient.acknowledged_at ? `<small>${escapeHtml(dateTime(recipient.acknowledged_at))}</small>` : ""}
      </div>
      <details class="driver-shift-recipient-support">
        <summary>Supporto accesso</summary>
        <p>Usa il link personale solo se il driver non riesce ad accedere dal link condiviso.</p>
        <div class="driver-shift-recipient-actions">
          <button type="button" class="secondary" data-copy-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Link personale</button>
          <button type="button" class="quiet" data-regenerate-shift-link="${recipient.id}">Rigenera link</button>
          ${credentialStatus !== "MISSING" && credentialStatus !== "REVOKED" ? `<button type="button" class="quiet" data-reset-driver-credential="${recipient.workforce_member_id}">Reimposta PIN</button>` : ""}
          ${credentialStatus !== "MISSING" && credentialStatus !== "REVOKED" ? `<button type="button" class="quiet" data-revoke-driver-credential="${recipient.workforce_member_id}">Revoca accesso</button>` : ""}
          <button type="button" class="quiet" data-revoke-shift-link="${recipient.id}" ${recipient.access_revoked ? "disabled" : ""}>Revoca link personale</button>
        </div>
      </details>
    </article>
  `;
  }).join("");
}


export function renderManualShareRecipients(element, recipients, selectedIds = new Set()) {
  if (!recipients.length) {
    element.innerHTML = '<p class="driver-shift-distribution-empty">Nessun destinatario disponibile per la condivisione manuale.</p>';
    return;
  }
  element.innerHTML = recipients.map((recipient) => `
    <label class="driver-shift-manual-recipient">
      <input type="checkbox" data-select-shift-recipient="${recipient.id}"
        ${selectedIds.has(recipient.id) ? "checked" : ""}
        ${recipient.readiness !== "READY" || recipient.access_revoked ? "disabled" : ""} />
      <span><strong>${escapeHtml(recipient.display_name)}</strong><small>${escapeHtml((recipient.available_channels || []).join(" · ") || "Contatti non configurati")}</small></span>
    </label>
  `).join("");
}

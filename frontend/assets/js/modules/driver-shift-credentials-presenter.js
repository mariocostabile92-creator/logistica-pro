import { escapeHtml } from "../utils/dom.js";


const LABELS = Object.freeze({
  ACTIVE: "Accesso pronto",
  RESET_REQUIRED: "PIN da reimpostare",
  REVOKED: "Accesso revocato",
  MISSING: "Accesso da preparare",
});


export function credentialStatusMap(model) {
  return new Map((model?.recipients || []).map((recipient) => [
    Number(recipient.workforce_member_id), recipient.credential_status || "MISSING",
  ]));
}


export function renderCredentialSummary(element, model) {
  if (!model) {
    element.innerHTML = '<p class="driver-shift-credentials-loading">Caricamento accessi...</p>';
    return;
  }
  const summary = model.summary;
  const complete = summary.recipients_total > 0
    && summary.credentials_ready === summary.recipients_total;
  element.innerHTML = `
    <div class="driver-shift-credentials-heading">
      <div>
        <p class="eyebrow">Credenziali personali</p>
        <h5>Accessi pronti: ${escapeHtml(String(summary.credentials_ready))}/${escapeHtml(String(summary.recipients_total))}</h5>
        <p>${complete
          ? "Tutti i driver della settimana hanno un accesso personale."
          : `${escapeHtml(String(summary.missing))} accessi da preparare.`}</p>
      </div>
      <button type="button" data-prepare-driver-credentials>
        ${summary.missing > 0 ? `Prepara ${escapeHtml(String(summary.missing))} accessi` : "Verifica accessi"}
      </button>
    </div>
    <dl class="driver-shift-credentials-summary">
      <div><dt>Destinatari</dt><dd>${escapeHtml(String(summary.recipients_total))}</dd></div>
      <div><dt>Pronti</dt><dd>${escapeHtml(String(summary.credentials_ready))}</dd></div>
      <div><dt>Da preparare</dt><dd>${escapeHtml(String(summary.missing))}</dd></div>
      <div><dt>Da reimpostare</dt><dd>${escapeHtml(String(summary.reset_required))}</dd></div>
      <div><dt>Revocati</dt><dd>${escapeHtml(String(summary.revoked))}</dd></div>
    </dl>
  `;
}


export function renderInitialCredentials(element, credentials, { reset = false } = {}) {
  if (!credentials?.length) {
    element.hidden = true;
    element.innerHTML = "";
    return;
  }
  element.hidden = false;
  element.innerHTML = `
    <p class="eyebrow">Consegna una tantum</p>
    <h5>${reset ? "Nuovo PIN creato" : `${escapeHtml(String(credentials.length))} nuovi accessi creati`}</h5>
    <p class="driver-shift-credentials-warning">Il PIN iniziale viene mostrato o esportato una sola volta. Successivamente potra essere soltanto reimpostato.</p>
    <div class="driver-shift-initial-credentials">
      ${credentials.slice(0, 3).map((credential) => `
        <div>
          <strong>${escapeHtml(credential.display_name)}</strong>
          ${credential.access_code ? `<span>Codice ${escapeHtml(credential.access_code)}</span>` : ""}
          <span>PIN ${escapeHtml(credential.initial_pin)}</span>
        </div>
      `).join("")}
      ${credentials.length > 3 ? `<small>Altri ${escapeHtml(String(credentials.length - 3))} accessi sono disponibili nel CSV.</small>` : ""}
    </div>
    ${reset ? "" : '<button type="button" data-download-initial-credentials>Scarica credenziali iniziali</button>'}
  `;
}


export function credentialLabel(status) {
  return LABELS[status || "MISSING"] || LABELS.MISSING;
}

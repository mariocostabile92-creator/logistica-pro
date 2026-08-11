import { escapeHtml } from "../utils/dom.js";


function metric(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${Number(value || 0)}</strong></div>`;
}


export function renderWorkforceContactCoverage(target, coverage) {
  const planning = coverage.active_planning_available
    ? `
      <div class="workforce-contact-planning" data-state="active">
        <div><p class="eyebrow">Planning ACTIVE #${Number(coverage.active_planning_id)}</p><strong>Copertura destinatari reali</strong></div>
        <div class="workforce-contact-recipient-metrics">
          ${metric("Destinatari", coverage.recipients_total)}
          ${metric("Telefono", coverage.recipients_phone_ready)}
          ${metric("Email", coverage.recipients_email_ready)}
          ${metric("Entrambi", coverage.recipients_both)}
          ${metric("Senza canale", coverage.recipients_no_channel)}
        </div>
      </div>`
    : `
      <div class="workforce-contact-planning" data-state="empty">
        <div><p class="eyebrow">Planning Driver</p><strong>Nessun planning ACTIVE</strong></div>
        <p>La copertura dei destinatari sarà disponibile dopo la pubblicazione dei turni.</p>
      </div>`;
  target.innerHTML = `
    <header>
      <div><p class="eyebrow">Contact readiness</p><h3>Copertura contatti</h3></div>
      <p>${Number(coverage.active_members || 0)} membri attivi su ${Number(coverage.total_members || 0)}</p>
    </header>
    <div class="workforce-contact-member-metrics">
      ${metric("Telefono validi", coverage.phone_valid)}
      ${metric("Email valide", coverage.email_valid)}
      ${metric("Entrambi", coverage.both_valid)}
      ${metric("Senza canale", coverage.no_channel)}
      ${metric("Telefono non validi", coverage.phone_invalid)}
      ${metric("Email non valide", coverage.email_invalid)}
    </div>
    ${planning}
  `;
}

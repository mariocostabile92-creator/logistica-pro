import { escapeHtml } from "../../utils/dom.js";

export const operationLabel = value =>
  value === "check_out" ? "Presa in carico" : "Rientro";

export const statusPresentation = value => ({
  not_started: { label: "Non iniziata", tone: "not_started", marker: "○" },
  generated: { label: "Generata", tone: "generated", marker: "●" },
  opened: { label: "Aperta", tone: "opened", marker: "●" },
  in_progress: { label: "In compilazione", tone: "in_progress", marker: "●" },
  completed: { label: "Completata", tone: "completed", marker: "●" },
  con_anomalia: { label: "Completata con anomalia", tone: "anomaly", marker: "!" },
  late: { label: "In ritardo", tone: "late", marker: "!" },
}[value] || { label: "Non classificata", tone: "unknown", marker: "?" });

export const dateParts = value => {
  const date = new Date(value);
  return {
    date: date.toLocaleDateString("it-IT"),
    time: date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
    full: date.toLocaleString("it-IT"),
  };
};

export const procedureDateParts = item => {
  const occurred = dateParts(item.occurred_at);
  const operational = item.operational_date
    ? new Date(`${item.operational_date}T12:00:00`).toLocaleDateString("it-IT")
    : occurred.date;
  return { ...occurred, date: operational };
};

export function journalCard(item, selectedId) {
  const status = statusPresentation(item.status);
  const occurred = procedureDateParts(item);
  return `<button type="button" class="jcr-item status-${status.tone} ${selectedId === item.id ? "active" : ""}"
    data-jcr-id="${escapeHtml(item.id)}" aria-pressed="${selectedId === item.id}">
    <header><strong>${escapeHtml(item.plate_snapshot)}</strong>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <dl><div><dt>Driver</dt><dd>${escapeHtml(item.declared_driver_identifier)}</dd></div>
      <div><dt>Procedura</dt><dd>${escapeHtml(operationLabel(item.operation_type))}</dd></div>
      <div><dt>Data</dt><dd>${escapeHtml(occurred.date)}</dd></div>
      <div><dt>Ora</dt><dd>${escapeHtml(occurred.time)}</dd></div></dl>
    <div class="jcr-card-meta"><span>${item.anomaly_present ? "Anomalia presente" : "Nessuna anomalia"}</span>
      <span>${item.media.length} allegati</span><span>${escapeHtml(item.origin)}</span></div>
    <span class="jcr-card-action">Apri dettaglio <b aria-hidden="true">›</b></span>
  </button>`;
}

export function infoSection(title, className, content) {
  return `<section class="jcr-detail-section ${className}"><h4>${title}</h4>${content}</section>`;
}

export function facts(rows) {
  return `<dl class="jcr-facts">${rows.map(([label, value]) =>
    `<div><dt>${label}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("")}</dl>`;
}

export function warningsSection(warnings = []) {
  if (!warnings.length) return infoSection("Avvisi smart", "jcr-smart-section",
    `<div class="jcr-empty"><strong>Nessun avviso operativo</strong><p>La procedura non presenta condizioni da verificare.</p></div>`);
  return infoSection("Avvisi smart", "jcr-smart-section",
    `<div class="jcr-warnings">${warnings.map(warning => `<article>
      <header><span aria-hidden="true">!</span><h5>${escapeHtml(warning.message)}</h5></header>
      <dl><div><dt>Origine</dt><dd>Driver Journal</dd></div>
        <div><dt>Motivazione</dt><dd>${escapeHtml(warning.message)}</dd></div>
        <div><dt>Suggerimento</dt><dd>Verificare i dati registrati prima di procedere.</dd></div></dl>
    </article>`).join("")}</div>`);
}

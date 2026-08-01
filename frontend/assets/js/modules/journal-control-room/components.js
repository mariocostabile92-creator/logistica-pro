import { escapeHtml } from "../../utils/dom.js";

export const operationLabel = value =>
  value === "check_out" ? "Presa in carico" : "Rientro";

export const statusPresentation = value => ({
  generated: { label: "Generata", tone: "generated", marker: "●" },
  opened: { label: "Aperta", tone: "opened", marker: "●" },
  in_progress: { label: "In compilazione", tone: "in_progress", marker: "●" },
  completed: { label: "Completata", tone: "completed", marker: "●" },
  con_anomalia: { label: "Completata con anomalia", tone: "anomaly", marker: "!" },
}[value] || { label: "Non classificata", tone: "unknown", marker: "?" });

const dateParts = value => {
  const date = new Date(value);
  return {
    date: date.toLocaleDateString("it-IT"),
    time: date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
    full: date.toLocaleString("it-IT"),
  };
};

export function journalCard(item, selectedId) {
  const status = statusPresentation(item.status);
  const occurred = dateParts(item.occurred_at);
  return `<button type="button" class="jcr-item status-${status.tone} ${selectedId === item.id ? "active" : ""}"
    data-jcr-id="${escapeHtml(item.id)}" aria-pressed="${selectedId === item.id}">
    <header><strong>${escapeHtml(item.plate_snapshot)}</strong>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <dl><div><dt>Driver</dt><dd>${escapeHtml(item.declared_driver_identifier)}</dd></div>
      <div><dt>Procedura</dt><dd>${escapeHtml(operationLabel(item.operation_type))}</dd></div>
      <div><dt>Data</dt><dd>${escapeHtml(occurred.date)}</dd></div>
      <div><dt>Ora</dt><dd>${escapeHtml(occurred.time)}</dd></div></dl>
    <span class="jcr-card-action">Apri dettaglio <b aria-hidden="true">›</b></span>
  </button>`;
}

function infoSection(title, className, content) {
  return `<section class="jcr-detail-section ${className}"><h4>${title}</h4>${content}</section>`;
}

function facts(rows) {
  return `<dl class="jcr-facts">${rows.map(([label, value]) =>
    `<div><dt>${label}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("")}</dl>`;
}

function warningsSection(warnings = []) {
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

function mediaSection(media = []) {
  if (!media.length) return infoSection("Allegati", "jcr-attachments",
    `<div class="jcr-empty"><strong>Nessun allegato</strong><p>Non risultano foto o video associati alla procedura.</p></div>`);
  return infoSection("Allegati", "jcr-attachments",
    `<header><strong>${media.length} ${media.length === 1 ? "allegato" : "allegati"}</strong></header>
    <div class="jcr-media">${media.map(entry => {
      const video = entry.media_type.startsWith("video");
      return `<article>${video
        ? `<video src="${escapeHtml(entry.url)}" controls preload="metadata"></video>`
        : `<img src="${escapeHtml(entry.url)}" alt="Foto allegata alla procedura">`}
        <strong>${video ? "Video" : "Foto"} ${entry.display_order + 1}</strong>
        <div><a href="${escapeHtml(entry.url)}" target="_blank" rel="noopener">Apri</a>
          <a href="${escapeHtml(entry.download_url || `${entry.url}?download=1`)}" download>Download</a></div>
        ${entry.id ? `<button type="button" class="jcr-media-delete" data-jcr-media-delete="${escapeHtml(entry.id)}">Elimina</button>` : ""}</article>`;
    }).join("")}</div>`);
}

export function journalDetail(item) {
  if (!item) return `<div class="view-state"><strong>Seleziona una procedura</strong><p>Apri una registrazione per consultarne i dettagli.</p></div>`;
  const status = statusPresentation(item.status);
  const occurred = dateParts(item.occurred_at);
  const equipment = item.equipment.length
    ? `<ul class="jcr-checklist">${item.equipment.map(entry =>
      `<li><strong>${escapeHtml(entry.equipment_label_snapshot)}</strong>
        <span>${escapeHtml(entry.equipment_status)}</span>${entry.note ? `<small>${escapeHtml(entry.note)}</small>` : ""}</li>`).join("")}</ul>`
    : `<div class="jcr-empty">Nessuna dotazione registrata.</div>`;
  const damage = item.damage_case_id
    ? `<div class="jcr-damage"><div><strong>${escapeHtml(item.damage_case_number)}</strong><span>${escapeHtml(item.damage_case_status)}</span></div><button type="button" class="jcr-detail-action" data-jcr-damage="${item.damage_case_id}">Apri pratica</button></div>`
    : item.anomaly_present ? `<div class="jcr-damage"><strong>Anomalia da gestire</strong><button type="button" class="jcr-detail-action" data-jcr-damage-new>Apri Danni</button></div>` : `<div class="jcr-empty">Nessuna anomalia dichiarata.</div>`;
  return `<button type="button" class="quiet jcr-back" data-jcr-back>← Torna alla lista</button>
    <header class="jcr-detail-hero"><div><p class="eyebrow">Procedura operativa</p>
      <h3>${escapeHtml(operationLabel(item.operation_type))}</h3></div>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <div class="jcr-detail-layout">
      ${infoSection("Driver", "jcr-driver", facts([["Driver dichiarato", item.declared_driver_identifier]]))}
      ${infoSection("Veicolo", "jcr-vehicle", facts([["Targa", item.plate_snapshot], ["Modello", item.vehicle_model || "Non registrato"]]))}
      ${infoSection("Procedura", "jcr-procedure", facts([
        ["Tipo", operationLabel(item.operation_type)], ["Data", occurred.date], ["Ora", occurred.time],
        ["Origine", item.origin], ["Documento", item.operational_document_id || "Non disponibile"],
      ]))}
      ${infoSection("Timeline", "jcr-timeline", `<ol><li><time>${escapeHtml(occurred.full)}</time><strong>${escapeHtml(status.label)}</strong></li></ol>`)}
      ${infoSection("Checklist", "jcr-checklist-section", `${facts([
        ["Km", item.odometer_km ?? "Non registrati"],
        ["Carburante", item.fuel_percentage == null ? "Non registrato" : `${item.fuel_percentage}%`],
        ["Pulizia", item.cleanliness_status || "Non registrata"],
        ["Note", item.operational_note || "Nessuna"],
      ])}${equipment}`)}
      ${infoSection("Anomalie", "jcr-anomalies", `${facts([["Descrizione", item.anomaly_description || "Nessuna"]])}${damage}`)}
      ${warningsSection(item.warnings)}
      ${mediaSection(item.permissions?.delete_media ? item.media : item.media.map(entry => ({ ...entry, id: null })))}
      ${infoSection("Azioni", "jcr-actions-section", `<div class="jcr-actions">
        ${item.receipt_url ? `<a class="header-config-button" href="${escapeHtml(item.receipt_url)}" target="_blank" rel="noopener">Apri documento operativo</a>` : ""}
        <button type="button" class="secondary" data-jcr-vehicle="${item.asset_id}">Apri dossier mezzo</button>
      </div>`)}
    </div>`;
}

export function journalKpis() {
  return [
    ["completed_today", "Completate oggi", "completed"],
    ["check_outs", "Prese in carico", "checkout"],
    ["check_ins", "Rientri", "checkin"],
    ["with_anomalies", "Anomalie", "anomaly"],
    ["incomplete", "In compilazione", "progress"],
  ].map(([key, label, tone]) => `<article class="jcr-kpi tone-${tone}">
    <strong data-jcr-kpi="${key}">0</strong><span>${label}</span><small>Dato operativo</small></article>`).join("");
}

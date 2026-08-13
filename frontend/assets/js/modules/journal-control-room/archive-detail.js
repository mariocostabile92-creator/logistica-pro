import { escapeHtml } from "../../utils/dom.js";
import { facts, infoSection, operationLabel, procedureDateParts, statusPresentation, warningsSection } from "./components.js";
import { journalMediaSection } from "./media-section.js";
import { driverDisplayName } from "./driver-display.js";

function equipmentSection(item) {
  if (!item.equipment.length) return `<div class="jcr-empty">Nessuna dotazione registrata.</div>`;
  return `<ul class="jcr-checklist">${item.equipment.map(entry => `<li><strong>${escapeHtml(entry.equipment_label_snapshot)}</strong>
    <span>${escapeHtml(entry.equipment_status)}</span>${entry.note ? `<small>${escapeHtml(entry.note)}</small>` : ""}</li>`).join("")}</ul>`;
}

function damageSection(item) {
  const details = facts([
    ["Descrizione", item.anomaly_description || "Nessuna"],
    ["Gravità", item.damage_case_severity || "Non classificata"],
    ["Categoria", "Non classificata"],
    ["Note", item.operational_note || "Nessuna"],
  ]);
  if (item.damage_case_id) return `${details}<div class="jcr-damage"><div><strong>${escapeHtml(item.damage_case_number)}</strong><span>${escapeHtml(item.damage_case_status)}</span></div>
    <button type="button" class="jcr-detail-action" data-jcr-damage="${item.damage_case_id}">Apri pratica danno</button></div>`;
  if (item.anomaly_present) return `${details}<div class="jcr-damage"><strong>Anomalia da gestire</strong><button type="button" class="jcr-detail-action" data-jcr-damage-new>Apri Danni</button></div>`;
  return `${details}<div class="jcr-empty">Nessuna anomalia dichiarata.</div>`;
}

function completeTimeline(item) {
  const events = [
    [item.created_at, "Generazione", "Procedura creata"],
    [item.opened_at, "Apertura", "Driver Journal aperto"],
    [item.in_progress_at, "Aggiornamento", "Compilazione avviata"],
    ...item.media.map(media => [media.received_at || media.uploaded_at, "Allegato", media.original_filename || "Media caricato"]),
    [item.anomaly_present ? item.occurred_at : null, "Anomalia", item.anomaly_description || "Anomalia dichiarata"],
    [!item.incomplete ? item.occurred_at : null, "Completamento", "Procedura completata"],
    [item.damage_case_id ? item.damage_case_created_at || item.occurred_at : null, "Pratica danno", item.damage_case_number || "Pratica collegata"],
  ].filter(([at]) => at).sort((a, b) => new Date(a[0]) - new Date(b[0]));
  return `<ol>${events.map(([at, title, description]) => `<li><time>${escapeHtml(procedureDateParts({ ...item, occurred_at: at }).full)}</time><strong>${escapeHtml(title)}</strong><span>${escapeHtml(description)}</span></li>`).join("")}</ol>`;
}

export function journalArchiveDetail(item) {
  if (!item) return `<div class="view-state"><strong>Seleziona una procedura</strong><p>Apri un giornale per consultarne il contenuto completo.</p></div>`;
  const status = statusPresentation(item.status);
  const occurred = procedureDateParts(item);
  return `<button type="button" class="quiet jcr-back" data-jcr-back>← Torna alla lista</button>
    <header class="jcr-detail-hero"><div><p class="eyebrow">Giornale di bordo completo</p><h3>${escapeHtml(operationLabel(item.operation_type))}</h3></div>
      <span class="jcr-status status-${status.tone}"><b aria-hidden="true">${status.marker}</b>${escapeHtml(status.label)}</span></header>
    <div class="jcr-detail-layout jcr-archive-full-detail">
      ${infoSection("Identificazione", "jcr-identification", facts([
        ["Driver", driverDisplayName(item)], ["Targa", item.plate_snapshot],
        ["Modello", item.vehicle_model || "Non registrato"], ["Procedura", operationLabel(item.operation_type)],
        ["Data operativa", occurred.date], ["Data e ora reali", occurred.full],
        ["Origine", item.origin], ["ID documento", item.operational_document_id || "Non disponibile"],
      ]))}
      ${infoSection("Dati operativi", "jcr-operational-data", facts([
        ["Chilometraggio", item.odometer_km ?? "Non registrato"],
        ["Carburante", item.fuel_percentage == null ? "Non registrato" : `${item.fuel_percentage}%`],
        ["Pulizia", item.cleanliness_status || "Non registrata"],
        ["Turno", item.operational_shift || "Non registrato"],
        ["Tipo registrazione", operationLabel(item.operation_type)], ["Note operative", item.operational_note || "Nessuna"],
      ]))}
      ${infoSection("Dotazioni e checklist", "jcr-checklist-section", equipmentSection(item))}
      ${infoSection("Anomalie", "jcr-anomalies", damageSection(item))}
      ${warningsSection(item.warnings)}
      ${journalMediaSection(item.media, Boolean(item.permissions?.delete_media), item)}
      ${infoSection("Timeline completa", "jcr-timeline", completeTimeline(item))}
      ${infoSection("Azioni", "jcr-actions-section", `<div class="jcr-actions">
        <button type="button" class="secondary" data-jcr-vehicle="${item.asset_id}">Apri dossier mezzo</button>
        ${item.damage_case_id ? `<button type="button" class="secondary" data-jcr-damage="${item.damage_case_id}">Apri pratica danno</button>` : ""}
      </div>`)}
    </div>`;
}

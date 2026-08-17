import { escapeHtml } from "../../utils/dom.js";
import { dateParts, infoSection } from "./components.js";

const mediaName = entry => entry.original_filename || `${entry.media_type.startsWith("video") ? "Video" : "Foto"} ${entry.display_order + 1}`;
const checkpointLabels = { CHECK_IN: "Presa in carico", CHECK_OUT: "Fine turno" };

const freshness = entry => {
  if (entry.reuse_detected) return { label: "Evidenza già utilizzata", tone: "warning" };
  return ({
    VERIFIED_SESSION_CAPTURE: { label: "Acquisita durante questo controllo", tone: "verified" },
    SAME_DAY_RECEIVED: { label: "Ricevuta nello stesso giorno operativo", tone: "same-day" },
    NOT_VERIFIABLE: { label: "Verifica data non disponibile per questo controllo storico", tone: "neutral" },
    DATE_MISMATCH: { label: "Data evidenza non coerente con il controllo corrente", tone: "warning" },
  })[entry.freshness_status] || { label: "Verifica data non disponibile per questo controllo storico", tone: "neutral" };
};

function mediaCards(media, canDelete, context) {
  if (!media.length) return `<div class="jcr-empty"><strong>Nessuna evidenza</strong><p>Non risultano foto o video per questo checkpoint.</p></div>`;
  return `<div class="jcr-media">${media.map(entry => {
    const video = entry.media_type.startsWith("video");
    const received = entry.received_at || entry.uploaded_at;
    const uploaded = received ? dateParts(received).full : "Data non disponibile";
    const verification = freshness(entry);
    return `<article>${video
      ? `<video src="${escapeHtml(entry.url)}" controls preload="metadata" aria-label="${escapeHtml(mediaName(entry))}"></video>`
      : `<img src="${escapeHtml(entry.url)}" alt="${escapeHtml(mediaName(entry))}">`}
      <div class="jcr-media-unavailable" hidden role="status">File non disponibile. Verifica che l'allegato sia ancora presente.</div>
      <strong>${escapeHtml(entry.evidence_slot || (video ? "Video del mezzo" : "Foto del mezzo"))}</strong>
      <small>Ricevuta: ${escapeHtml(uploaded)}</small>
      <dl class="jcr-media-evidence-facts"><div><dt>Verifica</dt><dd><span class="jcr-evidence-status ${verification.tone}">${escapeHtml(verification.label)}</span></dd></div>
        <div><dt>Giornale</dt><dd>${escapeHtml(entry.session_id || context.id || "Storico")}</dd></div>
        <div><dt>Data operativa</dt><dd>${escapeHtml(entry.operational_date || context.operational_date || "Non disponibile")}</dd></div>
        <div><dt>Mezzo</dt><dd>${escapeHtml(context.plate_snapshot || "Non disponibile")}</dd></div></dl>
      ${entry.freshness_warning ? `<p class="jcr-evidence-warning">${escapeHtml(entry.freshness_warning)}</p>` : ""}
      <small>${escapeHtml(mediaName(entry))}</small>
      <div><a href="${escapeHtml(entry.url)}" target="_blank" rel="noopener">Apri</a>
        <a href="${escapeHtml(entry.download_url || `${entry.url}?download=1`)}" download>Download</a></div>
      ${canDelete && entry.id ? `<button type="button" class="jcr-media-delete" data-jcr-media-delete="${escapeHtml(entry.id)}">Elimina</button>` : ""}</article>`;
  }).join("")}</div>`;
}

function checkpointBlock(checkpoint, media, canDelete, context) {
  const report = context.evidence?.checkpoints?.[checkpoint] || {};
  const mode = report.mode === "PHOTO" ? "Foto" : report.mode === "VIDEO" ? "Video" : "Non avviato";
  const status = report.completed ? "Completato" : report.evidence_complete ? "Pronto al completamento" : "Incompleto";
  const completedAt = report.completed_at ? dateParts(report.completed_at).full : "—";
  return `<section class="jcr-checkpoint-evidence" data-jcr-checkpoint="${checkpoint}"><header><div><span>${checkpoint}</span><h4>${checkpointLabels[checkpoint]}</h4></div><strong>${status}</strong></header>
    <dl class="jcr-checkpoint-summary"><div><dt>Modalità</dt><dd>${mode}</dd></div><div><dt>Completato</dt><dd>${completedAt}</dd></div></dl>
    ${mediaCards(media.filter(entry => entry.checkpoint === checkpoint), canDelete, context)}</section>`;
}

export function journalMediaSection(media = [], canDelete = false, context = {}) {
  const evidence = context.evidence || {};
  if (evidence.historical || !evidence.checkpoints || !Object.keys(evidence.checkpoints).length) {
    return infoSection("Evidenze", "jcr-attachments",
      `<p class="jcr-evidence-legacy">Policy evidenze IN/OUT non disponibile per questo Journal storico.</p>${mediaCards(media, canDelete, context)}`);
  }
  return infoSection("Allegati ed evidenze check-in / check-out", "jcr-attachments",
    `<div class="jcr-checkpoint-evidence-list">${checkpointBlock("CHECK_IN", media, canDelete, context)}${checkpointBlock("CHECK_OUT", media, canDelete, context)}</div>`);
}

export function wireJournalMediaFallback(root) {
  if (root.dataset.mediaFallbackReady) return;
  root.dataset.mediaFallbackReady = "true";
  root.addEventListener("error", event => {
    if (!event.target.matches(".jcr-media img,.jcr-media video")) return;
    event.target.hidden = true;
    const message = event.target.parentElement?.querySelector(".jcr-media-unavailable");
    if (message) message.hidden = false;
  }, true);
}

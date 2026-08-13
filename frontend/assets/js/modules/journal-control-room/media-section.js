import { escapeHtml } from "../../utils/dom.js";
import { dateParts, infoSection } from "./components.js";

const mediaName = entry => entry.original_filename || `${entry.media_type.startsWith("video") ? "Video" : "Foto"} ${entry.display_order + 1}`;

const freshness = entry => {
  if (entry.reuse_detected) return { label: "Evidenza già utilizzata", tone: "warning" };
  return ({
    VERIFIED_SESSION_CAPTURE: { label: "Acquisita durante questo controllo", tone: "verified" },
    SAME_DAY_RECEIVED: { label: "Ricevuta nello stesso giorno operativo", tone: "same-day" },
    NOT_VERIFIABLE: { label: "Verifica data non disponibile per questo controllo storico", tone: "neutral" },
    DATE_MISMATCH: { label: "Data evidenza non coerente con il controllo corrente", tone: "warning" },
  })[entry.freshness_status] || {
    label: "Verifica data non disponibile per questo controllo storico",
    tone: "neutral",
  };
};

export function journalMediaSection(media = [], canDelete = false, context = {}) {
  if (!media.length) return infoSection("Allegati", "jcr-attachments",
    `<div class="jcr-empty"><strong>Nessun allegato</strong><p>Non risultano foto o video associati alla procedura.</p></div>`);
  return infoSection("Allegati", "jcr-attachments",
    `<header class="jcr-media-summary"><strong>${media.length} ${media.length === 1 ? "allegato" : "allegati"}</strong></header>
    <div class="jcr-media">${media.map(entry => {
      const video = entry.media_type.startsWith("video");
      const received = entry.received_at || entry.uploaded_at;
      const uploaded = received ? dateParts(received).full : "Data non disponibile";
      const verification = freshness(entry);
      return `<article>${video
        ? `<video src="${escapeHtml(entry.url)}" controls preload="metadata" aria-label="${escapeHtml(mediaName(entry))}"></video>`
        : `<img src="${escapeHtml(entry.url)}" alt="${escapeHtml(mediaName(entry))}">`}
        <div class="jcr-media-unavailable" hidden role="status">File non disponibile. Verifica che l'allegato sia ancora presente.</div>
        <strong>${escapeHtml(entry.evidence_type === "video" || video ? "Video del mezzo" : "Foto del mezzo")}</strong>
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
    }).join("")}</div>`);
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

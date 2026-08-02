import { escapeHtml } from "../../utils/dom.js";
import { dateParts, infoSection } from "./components.js";

const mediaName = entry => entry.original_filename || `${entry.media_type.startsWith("video") ? "Video" : "Foto"} ${entry.display_order + 1}`;

export function journalMediaSection(media = [], canDelete = false) {
  if (!media.length) return infoSection("Allegati", "jcr-attachments",
    `<div class="jcr-empty"><strong>Nessun allegato</strong><p>Non risultano foto o video associati alla procedura.</p></div>`);
  return infoSection("Allegati", "jcr-attachments",
    `<header class="jcr-media-summary"><strong>${media.length} ${media.length === 1 ? "allegato" : "allegati"}</strong></header>
    <div class="jcr-media">${media.map(entry => {
      const video = entry.media_type.startsWith("video");
      const uploaded = entry.uploaded_at ? dateParts(entry.uploaded_at).full : "Data non disponibile";
      return `<article>${video
        ? `<video src="${escapeHtml(entry.url)}" controls preload="metadata" aria-label="${escapeHtml(mediaName(entry))}"></video>`
        : `<img src="${escapeHtml(entry.url)}" alt="${escapeHtml(mediaName(entry))}">`}
        <div class="jcr-media-unavailable" hidden role="status">File non disponibile. Verifica che l'allegato sia ancora presente.</div>
        <strong>${escapeHtml(mediaName(entry))}</strong><small>Caricato: ${escapeHtml(uploaded)}</small>
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

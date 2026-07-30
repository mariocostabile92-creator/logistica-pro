import { escapeHtml } from "../../utils/dom.js";

const size = value => value < 1024 * 1024
  ? `${Math.max(1, Math.round(value / 1024))} KB`
  : `${(value / 1024 / 1024).toFixed(1)} MB`;

function preview(item) {
  if (!item.preview_url) return '<span class="attachment-file-icon" aria-hidden="true">FILE</span>';
  if (item.mime_type.startsWith("image/")) {
    return `<img src="${escapeHtml(item.preview_url)}" alt="Anteprima ${escapeHtml(item.original_filename)}">`;
  }
  if (item.mime_type.startsWith("video/")) {
    return `<video src="${escapeHtml(item.preview_url)}" controls preload="metadata" aria-label="Anteprima ${escapeHtml(item.original_filename)}"></video>`;
  }
  return `<a class="attachment-file-icon" href="${escapeHtml(item.preview_url)}" target="_blank" rel="noopener" aria-label="Apri anteprima PDF">PDF</a>`;
}

export function renderAttachments(container, state, options = {}) {
  const title = options.title || "Allegati";
  const empty = state.loading
    ? '<p class="attachment-status">Caricamento allegati…</p>'
    : state.error
      ? `<p class="attachment-error" role="alert">${escapeHtml(state.error)}</p>`
      : '<p class="attachment-empty">Nessun allegato. PDF, foto e video saranno raccolti qui.</p>';
  container.innerHTML = `<section class="attachment-panel" aria-label="${escapeHtml(title)}">
    <header><div><h4>${escapeHtml(title)}</h4><p>${state.items.length} allegati</p></div>
      ${options.readOnly ? "" : `<label class="attachment-upload">Aggiungi allegato<input data-attachment-input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.mp4,.mov" hidden></label>`}
    </header>
    <div class="attachment-grid">${state.items.length ? state.items.map(item => `
      <article class="attachment-card">${preview(item)}
        <div><strong>${escapeHtml(item.original_filename)}</strong><small>${escapeHtml(size(item.size))} · ${escapeHtml(new Date(item.created_at).toLocaleString("it-IT"))}</small></div>
        <div class="attachment-actions">
          ${item.preview_url ? `<a href="${escapeHtml(item.preview_url)}" target="_blank" rel="noopener">Preview</a>` : ""}
          <a href="${escapeHtml(item.download_url)}">Download</a>
          ${options.readOnly ? "" : `<button type="button" class="quiet" data-attachment-delete="${escapeHtml(item.id)}">Elimina</button>`}
        </div>
      </article>`).join("") : empty}</div>
    <p class="attachment-feedback" data-attachment-feedback aria-live="polite"></p>
  </section>`;
}

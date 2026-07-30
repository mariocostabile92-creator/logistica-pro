import { escapeHtml } from "../../utils/dom.js";

const fileSize = value => value < 1024 * 1024
  ? `${Math.max(1, Math.round(value / 1024))} KB`
  : `${(value / 1024 / 1024).toFixed(1)} MB`;

export function renderAttachmentDraft(container, state, options = {}) {
  const title = options.title || "Allegati";
  const accept = options.accept || ".pdf,.jpg,.jpeg,.png,.webp";
  container.innerHTML = `
    <section class="attachment-draft" aria-label="${escapeHtml(title)}">
      <div><h4>${escapeHtml(title)}</h4><p>Trascina qui i file oppure selezionali dal dispositivo.</p></div>
      <label class="attachment-dropzone${state.uploading ? " is-loading" : ""}" data-attachment-dropzone>
        <strong>${state.uploading ? "Caricamento in corso…" : "Trascina e rilascia"}</strong>
        <span>oppure</span><span class="attachment-select-button">Seleziona file</span>
        <input data-attachment-draft-input type="file" multiple accept="${escapeHtml(accept)}" hidden
          ${state.uploading ? "disabled" : ""}>
      </label>
      <div class="attachment-draft-list">${state.files.map((file, index) => `
        <div class="attachment-draft-file">
          <span><strong>${escapeHtml(file.name)}</strong><small>${escapeHtml(fileSize(file.size))}</small></span>
          <button type="button" class="quiet" data-attachment-draft-remove="${index}"
            ${state.uploading ? "disabled" : ""}>Rimuovi</button>
        </div>`).join("")}</div>
      ${state.error ? `<p class="attachment-error" role="alert">${escapeHtml(state.error)}</p>
        <button type="button" class="secondary attachment-retry" data-attachment-retry>Riprova upload</button>` : ""}
      <p class="attachment-feedback" role="status" aria-live="polite">${escapeHtml(state.feedback)}</p>
    </section>`;
}


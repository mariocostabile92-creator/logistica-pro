import { uploadAttachment } from "./api.js";
import { renderAttachmentDraft } from "./draft-renderer.js";
import { attachmentDraftState } from "./draft-state.js";

export function createAttachmentDraft(container, options = {}) {
  const state = attachmentDraftState(container);
  const render = () => renderAttachmentDraft(container, state, options);
  const addFiles = files => {
    const existing = new Set(state.files.map(file => `${file.name}:${file.size}:${file.lastModified}`));
    state.files.push(...[...files].filter(file => !existing.has(`${file.name}:${file.size}:${file.lastModified}`)));
    state.error = "";
    state.feedback = state.files.length ? `${state.files.length} file pronti per il salvataggio.` : "";
    render();
  };
  const reset = ({ entityId = null, record = null } = {}) => {
    Object.assign(state, {
      files: [], uploading: false, error: "", feedback: "", entityId, record,
    });
    render();
  };
  const uploadPending = async (entityType, entityId = state.entityId) => {
    if (!state.files.length) return [];
    state.uploading = true;
    state.error = "";
    state.feedback = "Caricamento allegati in corso…";
    render();
    const uploaded = [];
    try {
      while (state.files.length) {
        const file = state.files[0];
        uploaded.push(await uploadAttachment(entityType, entityId, file));
        state.files.shift();
      }
      state.feedback = "Allegati caricati correttamente.";
      return uploaded;
    } catch (error) {
      state.error = `Record salvato, ma upload incompleto: ${error.message}`;
      state.feedback = "I file già caricati non saranno duplicati. Riprova per completare.";
      throw error;
    } finally {
      state.uploading = false;
      render();
    }
  };
  container.onchange = event => {
    if (event.target.matches("[data-attachment-draft-input]")) addFiles(event.target.files);
  };
  container.ondragover = event => {
    if (!event.target.closest("[data-attachment-dropzone]")) return;
    event.preventDefault();
  };
  container.ondrop = event => {
    if (!event.target.closest("[data-attachment-dropzone]")) return;
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  };
  container.onclick = event => {
    const remove = event.target.closest("[data-attachment-draft-remove]");
    if (remove) {
      state.files.splice(Number(remove.dataset.attachmentDraftRemove), 1);
      state.feedback = state.files.length ? `${state.files.length} file pronti per il salvataggio.` : "";
      render();
    }
    if (event.target.closest("[data-attachment-retry]")) {
      container.dispatchEvent(new CustomEvent("attachments:retry", { bubbles: true }));
    }
  };
  render();
  return {
    reset,
    uploadPending,
    setEntity(record) {
      state.entityId = record.id;
      state.record = record;
    },
    get entityId() { return state.entityId; },
    get record() { return state.record; },
    get uploading() { return state.uploading; },
    get hasPending() { return state.files.length > 0; },
  };
}


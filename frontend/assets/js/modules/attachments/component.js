import {
  deleteAttachment, listAttachments, listVehicleAttachments, uploadAttachment,
} from "./api.js";
import { renderAttachments } from "./renderer.js";
import { attachmentState } from "./state.js";

export async function mountAttachments(container, options) {
  if (!container || !options?.entityId) return;
  const state = attachmentState(container);
  Object.assign(state, {
    entityType: options.entityType, entityId: Number(options.entityId),
    loading: true, error: "",
  });
  renderAttachments(container, state, options);
  try {
    const response = options.aggregateVehicle
      ? await listVehicleAttachments(state.entityId)
      : await listAttachments(state.entityType, state.entityId);
    state.items = response.items || [];
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    renderAttachments(container, state, options);
  }
  if (options.readOnly) return;
  container.onchange = async event => {
    if (!event.target.matches("[data-attachment-input]")) return;
    const files = [...event.target.files];
    state.loading = true;
    renderAttachments(container, state, options);
    try {
      for (const file of files) {
        state.items.unshift(await uploadAttachment(state.entityType, state.entityId, file));
      }
    } catch (error) {
      state.error = error.message;
    } finally {
      state.loading = false;
      renderAttachments(container, state, options);
    }
  };
  container.onclick = async event => {
    const attachmentId = event.target.closest("[data-attachment-delete]")?.dataset.attachmentDelete;
    if (!attachmentId || !window.confirm("Eliminare definitivamente questo allegato?")) return;
    await deleteAttachment(attachmentId);
    state.items = state.items.filter(item => item.id !== attachmentId);
    renderAttachments(container, state, options);
  };
}

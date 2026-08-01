import { deleteMedia, uploadMedia } from "./api.js?v=dj4";
import { state } from "./state.js?v=dj4";

const input = () => document.getElementById("mediaInput");
const preview = () => document.getElementById("mediaPreview");
let uploading = false;

async function send(file, showError, failedId = null) {
  try {
    const saved = await uploadMedia(state.sessionId, state.token, file);
    if (failedId) state.media = state.media.filter(item => item.id !== failedId);
    state.media.push({ ...saved, preview: URL.createObjectURL(file), file });
  } catch (error) {
    const id = failedId || `failed-${crypto.randomUUID()}`;
    const existing = state.media.find(item => item.id === id);
    if (existing) existing.error = error.message;
    else state.media.push({ id, file, error: error.message, failed: true });
    showError("Uno o più file non sono stati caricati. Puoi riprovare solo quelli non riusciti.");
  }
}

function render(showError) {
  preview().innerHTML = "";
  state.media.forEach(item => {
    const card = document.createElement("div");
    card.className = `media-card${item.failed ? " media-card-failed" : ""}`;
    if (item.failed) {
      const message = document.createElement("p");
      message.textContent = `${item.file.name}: ${item.error}`;
      const retry = document.createElement("button");
      retry.type = "button"; retry.textContent = "Riprova";
      retry.addEventListener("click", async () => {
        retry.disabled = true; await send(item.file, showError, item.id); render(showError);
      });
      card.append(message, retry); preview().append(card); return;
    }
    const media = item.file?.type.startsWith("video/") ? document.createElement("video") : document.createElement("img");
    media.src = item.preview;
    if (media.tagName === "VIDEO") {
      media.controls = true; media.preload = "metadata"; media.setAttribute("aria-label", "Anteprima video mezzo");
    } else media.alt = "Anteprima foto mezzo";
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Rimuovi";
    remove.addEventListener("click", async () => {
      remove.disabled = true; await deleteMedia(state.sessionId, state.token, item.id);
      URL.revokeObjectURL(item.preview); state.media = state.media.filter(entry => entry.id !== item.id); render(showError);
    });
    card.append(media, remove); preview().append(card);
  });
}

export function initMedia(showError) {
  input().addEventListener("change", async event => {
    if (uploading) return;
    uploading = true; input().disabled = true; showError("");
    for (const file of event.target.files) await send(file, showError);
    input().value = ""; input().disabled = false; uploading = false; render(showError);
  });
}

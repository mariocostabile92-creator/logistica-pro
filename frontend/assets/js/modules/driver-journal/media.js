import { deleteMedia, uploadMedia } from "./api.js";
import { state } from "./state.js";
const input = () => document.getElementById("mediaInput");
const preview = () => document.getElementById("mediaPreview");
function render() {
  preview().innerHTML = "";
  state.media.forEach(item => {
    const card = document.createElement("div"); card.className = "media-card";
    const image = document.createElement("img"); image.src = item.preview; image.alt = "Anteprima foto mezzo";
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Rimuovi";
    remove.addEventListener("click", async () => { await deleteMedia(state.sessionId, state.token, item.id); URL.revokeObjectURL(item.preview); state.media = state.media.filter(media => media.id !== item.id); render(); });
    card.append(image, remove); preview().append(card);
  });
}
export function initMedia(showError) {
  input().addEventListener("change", async event => {
    showError("");
    for (const file of event.target.files) {
      try { const saved = await uploadMedia(state.sessionId, state.token, file); state.media.push({...saved, preview: URL.createObjectURL(file)}); render(); }
      catch (error) { showError(error.message); }
    }
    input().value = "";
  });
}

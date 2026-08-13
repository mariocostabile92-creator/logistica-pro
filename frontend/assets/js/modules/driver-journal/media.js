import { deleteMedia, uploadMedia } from "./api.js?v=djh1";
import { evidenceProgress, evidenceStatusLabel } from "./evidence.js?v=djh1";
import { state } from "./state.js?v=djh1";

const input = () => document.getElementById("mediaInput");
const photoInput = () => document.getElementById("photoCaptureInput");
const videoInput = () => document.getElementById("videoCaptureInput");
const preview = () => document.getElementById("mediaPreview");
let uploading = false;

const requiredEvidence = () => state.configuration?.media?.required || { photo: 1, video: 1 };

function updateProgress() {
  const progress = evidenceProgress(state.media, requiredEvidence());
  const root = document.getElementById("evidenceProgress");
  if (root) root.innerHTML = [
    ["photo", "Foto"], ["video", "Video"],
  ].map(([type, label]) => `<article class="${progress.counts[type] >= progress.required[type] ? "complete" : ""}">
    <strong>${label}: ${progress.counts[type]}/${progress.required[type]}</strong>
    <span>${progress.counts[type] >= progress.required[type] ? "Presente" : "Obbligatorio"}</span>
  </article>`).join("");
  const completeButton = document.getElementById("nextButton");
  if (completeButton && state.step === 7) completeButton.disabled = !progress.complete || state.submitting;
  return progress;
}

async function send(file, showError, options = {}, failedId = null) {
  try {
    const evidenceType = file.type.startsWith("video/") ? "video" : "photo";
    const saved = await uploadMedia(state.sessionId, state.token, file, {
      capturedAt: options.capturedAt || null,
      captureSource: options.captureSource || "file",
      evidenceSlot: evidenceType,
    });
    if (failedId) state.media = state.media.filter(item => item.id !== failedId);
    if (saved.replaced_media_id) {
      const replaced = state.media.find(item => item.id === saved.replaced_media_id);
      if (replaced?.preview?.startsWith("blob:")) URL.revokeObjectURL(replaced.preview);
      state.media = state.media.filter(item => item.id !== saved.replaced_media_id);
    }
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
        retry.disabled = true;
        await send(item.file, showError, { captureSource: "file" }, item.id);
        render(showError);
      });
      card.append(message, retry); preview().append(card); return;
    }
    const video = item.evidence_type === "video" || item.media_type === "video" || item.file?.type.startsWith("video/");
    const media = video ? document.createElement("video") : document.createElement("img");
    media.src = item.preview || item.url;
    if (video) {
      media.controls = true; media.preload = "metadata"; media.setAttribute("aria-label", "Anteprima video mezzo");
    } else media.alt = "Anteprima foto mezzo";
    const verification = document.createElement("p");
    verification.className = `evidence-verification${item.freshness_warning || item.reuse_detected ? " warning" : ""}`;
    verification.textContent = item.freshness_warning || evidenceStatusLabel(item);
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Rifai / sostituisci";
    remove.addEventListener("click", async () => {
      remove.disabled = true; await deleteMedia(state.sessionId, state.token, item.id);
      if (item.preview?.startsWith("blob:")) URL.revokeObjectURL(item.preview);
      state.media = state.media.filter(entry => entry.id !== item.id); render(showError);
    });
    card.append(media, verification, remove); preview().append(card);
  });
  updateProgress();
}

async function handleSelection(event, showError, captureSource) {
  if (uploading) return;
  uploading = true;
  event.currentTarget.disabled = true;
  showError("");
  const capturedAt = captureSource === "camera" ? new Date().toISOString() : null;
  for (const file of event.currentTarget.files) {
    await send(file, showError, { captureSource, capturedAt });
  }
  event.currentTarget.value = "";
  event.currentTarget.disabled = false;
  uploading = false;
  render(showError);
}

export function initMedia(showError) {
  input().addEventListener("change", event => handleSelection(event, showError, "file"));
  photoInput().addEventListener("change", event => handleSelection(event, showError, "camera"));
  videoInput().addEventListener("change", event => handleSelection(event, showError, "camera"));
  render(showError);
}

export { updateProgress };

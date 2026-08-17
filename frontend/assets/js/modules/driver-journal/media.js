import { completeCheckpoint, deleteMedia, startCheckpoint, uploadMedia } from "./api.js?v=djh2";
import { CHECKPOINTS, PHOTO_SLOTS, checkpointProgress, evidenceProgress, evidenceStatusLabel } from "./evidence.js?v=djh2";
import { state } from "./state.js?v=djh2";
import { escapeHtml } from "../../utils/dom.js";

const CHECKPOINT_LABELS = {
  CHECK_IN: "Controllo presa in carico",
  CHECK_OUT: "Controllo fine turno",
};
const SLOT_LABELS = {
  FRONT: "Anteriore", REAR: "Posteriore", LEFT: "Lato sinistro",
  RIGHT: "Lato destro", ODOMETER: "Contachilometri", VIDEO: "Video continuo",
};
let uploading = false;
let showErrorHandler = () => {};

const serverCheckpoint = checkpoint => state.evidence?.checkpoints?.[checkpoint] || {};
const progressFor = checkpoint => checkpointProgress(
  state.media,
  checkpoint,
  serverCheckpoint(checkpoint).mode || null,
  serverCheckpoint(checkpoint).completed || false,
);

function updateProgress() {
  const progress = evidenceProgress(state.media, state.evidence);
  const root = document.getElementById("evidenceProgress");
  if (root) root.innerHTML = CHECKPOINTS.map(checkpoint => {
    const item = progress.checkpoints?.[checkpoint] || {};
    const done = item.completed;
    const present = item.presentSlots?.length || 0;
    const required = item.requiredSlots?.length || (item.mode ? 1 : 0);
    const detail = item.mode === "VIDEO"
      ? (done ? "Video completato" : present ? "Video caricato" : "Video mancante")
      : `${present}/${required || 5}`;
    return `<article class="${done ? "complete" : ""}"><strong>${CHECKPOINT_LABELS[checkpoint]}</strong><span>${detail}</span></article>`;
  }).join("");
  const completeButton = document.getElementById("nextButton");
  if (completeButton && state.step === 7) completeButton.disabled = !progress.complete || state.submitting;
  return progress;
}

async function chooseMode(checkpoint, mode) {
  showErrorHandler("");
  try {
    const response = await startCheckpoint(state.sessionId, state.token, checkpoint, mode);
    state.evidence = response.evidence;
    state.media = response.media || state.media;
    render();
  } catch (error) {
    showErrorHandler(error.message);
  }
}

async function send(file, checkpoint, mode, slot, failedId = null) {
  try {
    const saved = await uploadMedia(state.sessionId, state.token, file, {
      capturedAt: new Date().toISOString(), captureSource: "camera",
      checkpoint, evidenceMode: mode, evidenceSlot: slot,
    });
    if (failedId) state.media = state.media.filter(item => item.id !== failedId);
    if (saved.replaced_media_id) {
      const replaced = state.media.find(item => item.id === saved.replaced_media_id);
      if (replaced?.preview?.startsWith("blob:")) URL.revokeObjectURL(replaced.preview);
      state.media = state.media.filter(item => item.id !== saved.replaced_media_id);
    }
    state.media.push({ ...saved, preview: URL.createObjectURL(file), file });
    state.evidence = saved.evidence || state.evidence;
  } catch (error) {
    const id = failedId || `failed-${crypto.randomUUID()}`;
    const existing = state.media.find(item => item.id === id);
    const failure = { id, file, checkpoint, evidence_mode: mode, evidence_slot: slot, error: error.message, failed: true };
    if (existing) Object.assign(existing, failure); else state.media.push(failure);
    showErrorHandler("Il file non è stato caricato. Riprova l'evidenza indicata.");
  }
}

async function selectFile(input) {
  if (uploading || !input.files?.length) return;
  uploading = true;
  input.disabled = true;
  showErrorHandler("");
  const { checkpoint, mode, slot } = input.dataset;
  await send(input.files[0], checkpoint, mode, slot);
  input.value = "";
  input.disabled = false;
  uploading = false;
  render();
}

async function finishCheckpoint(checkpoint) {
  showErrorHandler("");
  try {
    const response = await completeCheckpoint(state.sessionId, state.token, checkpoint);
    state.evidence = response.evidence;
    state.media = response.media || state.media;
    render();
  } catch (error) {
    showErrorHandler(error.message);
  }
}

function mediaCard(item, locked) {
  const mediaId = escapeHtml(item.id || "");
  if (item.failed) return `<article class="media-card media-card-failed" data-media-id="${mediaId}"><p>${escapeHtml(item.file?.name || "File")}: ${escapeHtml(item.error || "Caricamento non riuscito")}</p><button type="button" data-retry-media="${mediaId}">Riprova</button></article>`;
  const video = item.evidence_mode === "VIDEO" || item.media_type === "video";
  const source = escapeHtml(item.preview || item.url || "");
  const label = escapeHtml(SLOT_LABELS[item.evidence_slot] || item.evidence_slot || "Evidenza");
  const verification = escapeHtml(item.freshness_warning || evidenceStatusLabel(item));
  return `<article class="media-card" data-media-id="${mediaId}">${video
    ? `<video src="${source}" controls preload="metadata" aria-label="${label}"></video>`
    : `<img src="${source}" alt="${label}">`}
    <strong>${label}</strong><p class="evidence-verification${item.freshness_warning || item.reuse_detected ? " warning" : ""}">${verification}</p>
    ${locked ? `<span class="checkpoint-locked">Controllo completato</span>` : `<button type="button" data-remove-media="${mediaId}">Rifai / sostituisci</button>`}</article>`;
}

function captureControls(checkpoint, progress) {
  if (!progress.mode) return `<div class="checkpoint-mode-picker"><p>Scegli la modalità per questo controllo.</p>
    <button type="button" data-checkpoint-mode="PHOTO" data-checkpoint="${checkpoint}">Foto</button>
    <button type="button" data-checkpoint-mode="VIDEO" data-checkpoint="${checkpoint}">Video</button></div>`;
  if (progress.completed) return "";
  if (progress.mode === "VIDEO") return `<div class="video-guidance"><strong>Video continuo richiesto</strong><p>Riprendi lentamente tutti e quattro i lati del mezzo.</p><p>Termina il video inquadrando chiaramente il contachilometri.</p>
    <label class="upload-button">${progress.presentSlots.includes("VIDEO") ? "Registra di nuovo" : "Registra video"}<input type="file" accept="video/mp4,video/quicktime" capture="environment" hidden data-evidence-input data-checkpoint="${checkpoint}" data-mode="VIDEO" data-slot="VIDEO"></label></div>`;
  return `<div class="checkpoint-slots">${PHOTO_SLOTS.map(slot => {
    const present = progress.presentSlots.includes(slot);
    return `<label class="checkpoint-slot ${present ? "is-present" : "is-missing"}"><span><strong>${SLOT_LABELS[slot]}</strong><small>${present ? "CARICATA" : "MANCANTE"}</small></span><span class="slot-action">${present ? "Rifai" : "Scatta"}</span><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden data-evidence-input data-checkpoint="${checkpoint}" data-mode="PHOTO" data-slot="${slot}"></label>`;
  }).join("")}</div>`;
}

function checkpointCard(checkpoint) {
  const progress = progressFor(checkpoint);
  const lockedBySequence = checkpoint === "CHECK_OUT" && !progressFor("CHECK_IN").completed;
  const media = state.media.filter(item => item.checkpoint === checkpoint);
  if (lockedBySequence) return `<article class="journal-checkpoint is-locked" data-checkpoint-card="${checkpoint}"><header><div><span>CHECK-OUT</span><h3>${CHECKPOINT_LABELS[checkpoint]}</h3></div><strong>In attesa</strong></header><p>Completa prima il controllo presa in carico.</p></article>`;
  return `<article class="journal-checkpoint${progress.completed ? " is-complete" : ""}" data-checkpoint-card="${checkpoint}">
    <header><div><span>${checkpoint === "CHECK_IN" ? "CHECK-IN" : "CHECK-OUT"}</span><h3>${CHECKPOINT_LABELS[checkpoint]}</h3></div><strong>${progress.completed ? "COMPLETO" : progress.mode || "DA AVVIARE"}</strong></header>
    ${captureControls(checkpoint, progress)}
    ${media.length ? `<div class="media-grid">${media.map(item => mediaCard(item, progress.completed)).join("")}</div>` : ""}
    ${progress.mode && !progress.completed ? `<button type="button" class="checkpoint-complete" data-complete-checkpoint="${checkpoint}" ${progress.evidenceComplete ? "" : "disabled"}>${checkpoint === "CHECK_IN" ? "Completa presa in carico" : "Completa controllo fine turno"}</button>` : ""}
  </article>`;
}

function wire() {
  const root = document.getElementById("checkpointControls");
  root.querySelectorAll("[data-checkpoint-mode]").forEach(button => button.addEventListener("click", () => chooseMode(button.dataset.checkpoint, button.dataset.checkpointMode)));
  root.querySelectorAll("[data-evidence-input]").forEach(input => input.addEventListener("change", () => selectFile(input)));
  root.querySelectorAll("[data-complete-checkpoint]").forEach(button => button.addEventListener("click", () => finishCheckpoint(button.dataset.completeCheckpoint)));
  root.querySelectorAll("[data-remove-media]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await deleteMedia(state.sessionId, state.token, button.dataset.removeMedia);
      state.media = state.media.filter(item => item.id !== button.dataset.removeMedia);
      render();
    } catch (error) { showErrorHandler(error.message); button.disabled = false; }
  }));
  root.querySelectorAll("[data-retry-media]").forEach(button => button.addEventListener("click", async () => {
    const item = state.media.find(entry => entry.id === button.dataset.retryMedia);
    if (!item) return;
    await send(item.file, item.checkpoint, item.evidence_mode, item.evidence_slot, item.id);
    render();
  }));
}

function render() {
  const root = document.getElementById("checkpointControls");
  if (!root) return;
  root.innerHTML = CHECKPOINTS.map(checkpointCard).join("");
  wire();
  updateProgress();
}

export function initMedia(showError) {
  showErrorHandler = showError;
  render();
}

export { render as renderEvidence, updateProgress };

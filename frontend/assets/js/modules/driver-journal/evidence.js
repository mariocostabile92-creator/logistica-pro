export const CHECKPOINTS = Object.freeze(["CHECK_IN", "CHECK_OUT"]);
export const PHOTO_SLOTS = Object.freeze(["FRONT", "REAR", "LEFT", "RIGHT", "ODOMETER"]);
export const VIDEO_SLOTS = Object.freeze(["VIDEO"]);

const slotSet = (media, checkpoint) => new Set(media
  .filter(item => !item.failed && item.checkpoint === checkpoint)
  .map(item => item.evidence_slot));

export function checkpointProgress(media = [], checkpoint, mode = null, completed = false) {
  const slots = mode === "PHOTO" ? PHOTO_SLOTS : mode === "VIDEO" ? VIDEO_SLOTS : [];
  const present = slotSet(media, checkpoint);
  const blocked = media.filter(item => item.checkpoint === checkpoint
    && (item.freshness_status === "DATE_MISMATCH" || Boolean(item.reuse_detected)));
  const missing = slots.filter(slot => !present.has(slot));
  return {
    checkpoint, mode, requiredSlots: slots, presentSlots: [...present], missing, blocked,
    evidenceComplete: Boolean(mode) && !missing.length && !blocked.length,
    completed: Boolean(completed),
  };
}

export function evidenceProgress(media = [], evidence = null) {
  if (evidence?.historical) return { ...evidence, complete: true };
  const server = evidence?.checkpoints || {};
  const checkpoints = Object.fromEntries(CHECKPOINTS.map(checkpoint => {
    const item = server[checkpoint] || {};
    return [checkpoint, checkpointProgress(
      media,
      checkpoint,
      item.mode || null,
      item.completed || false,
    )];
  }));
  const blocked = Object.values(checkpoints).flatMap(item => item.blocked);
  const missing = Object.values(checkpoints).flatMap(item => item.missing);
  return {
    checkpoints, blocked, missing,
    complete: CHECKPOINTS.every(checkpoint => checkpoints[checkpoint].completed),
  };
}

export function evidenceStatusLabel(item) {
  if (item.reuse_detected) return "Evidenza già utilizzata";
  return ({
    VERIFIED_SESSION_CAPTURE: "Acquisita durante questo controllo",
    SAME_DAY_RECEIVED: "Ricevuta nello stesso giorno operativo",
    NOT_VERIFIABLE: "Data non verificabile",
    DATE_MISMATCH: "Data non coerente",
  })[item.freshness_status] || "Verifica in attesa";
}

export const DEFAULT_REQUIREMENTS = Object.freeze({ photo: 1, video: 1 });

const evidenceType = item => item.evidence_type
  || (item.media_type === "video" || item.file?.type?.startsWith("video/") ? "video" : "photo");

export function evidenceProgress(media = [], required = DEFAULT_REQUIREMENTS) {
  const valid = media.filter(item => !item.failed);
  const counts = {
    photo: valid.filter(item => evidenceType(item) === "photo").length,
    video: valid.filter(item => evidenceType(item) === "video").length,
  };
  const blocked = valid.filter(item =>
    item.freshness_status === "DATE_MISMATCH" || Boolean(item.reuse_detected)
  );
  const missing = Object.entries(required).filter(([type, count]) =>
    counts[type] < Number(count)
  ).map(([type]) => type);
  return {
    counts,
    required,
    missing,
    blocked,
    complete: missing.length === 0 && blocked.length === 0,
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

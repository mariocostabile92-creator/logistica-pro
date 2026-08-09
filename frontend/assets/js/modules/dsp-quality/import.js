export const QUALITY_MAX_FILE_BYTES = 8 * 1024 * 1024;


export function validateQualityFile(file) {
  if (!file) return "Seleziona una scorecard PDF.";
  const pdfName = String(file.name || "").toLowerCase().endsWith(".pdf");
  const pdfType = !file.type || file.type === "application/pdf";
  if (!pdfName || !pdfType) return "Formato non supportato. Seleziona un file PDF.";
  if (file.size > QUALITY_MAX_FILE_BYTES) return "Il file supera la dimensione massima di 8 MB.";
  return null;
}


export function formatQualityFileSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


export function qualityActionLabel(action) {
  return {
    CREATE: "Nuova scorecard",
    NO_OP: "Questa scorecard è già stata importata.",
    NEW_REVISION: "È già presente una scorecard per questa settimana. Verrà creata una nuova revisione.",
  }[action] || "Stato importazione da verificare";
}


export function qualityErrorMessage(error, stage = "preview") {
  if (error?.name === "AbortError") return null;
  if (error?.status === 413) return "Il file supera la dimensione massima consentita.";
  if (error?.status === 415) return "Formato non supportato. Seleziona un file PDF.";
  if (error?.status === 403) return "Non disponi del permesso per importare scorecard.";
  if (error?.status === 409) return "La preview non è più valida. Analizza nuovamente il file.";
  if (error?.status === 422) return "La scorecard non è riconosciuta o contiene dati non validi.";
  return stage === "import"
    ? "Importazione non riuscita. Riprova senza modificare il file."
    : "Analisi non riuscita. Controlla il file e riprova.";
}

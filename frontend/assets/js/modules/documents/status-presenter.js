export const DOCUMENT_TYPES = {
  carta_circolazione: "Carta di circolazione",
  assicurazione: "Assicurazione",
  revisione: "Revisione",
  bollo: "Bollo",
  autorizzazione: "Autorizzazione",
  manuale: "Libretto uso e manutenzione",
  contratto_noleggio: "Documentazione noleggio",
  contratto_leasing: "Documentazione leasing",
  manutenzione: "Documento di manutenzione",
  certificazione: "Certificazione",
  altro: "Documento generico",
};

export const DOCUMENT_STATUSES = {
  completo: "Completo",
  file_mancante: "File mancante",
  in_scadenza: "In scadenza",
  scaduto: "Scaduto",
  senza_scadenza: "Senza scadenza",
  archiviato: "Archiviato",
};

export const documentTypeLabel = value => DOCUMENT_TYPES[value] || "Documento";
export const documentStatusLabel = value => DOCUMENT_STATUSES[value] || "Non classificato";

export function validityExplanation(item) {
  if (item.status_reason) return item.status_reason;
  if (item.status === "file_mancante") return "Il record non ha allegati validi nell'Attachment Engine.";
  if (item.status === "senza_scadenza") return "Il documento non prevede una data di scadenza.";
  if (item.status === "archiviato") return "Il documento è stato archiviato e resta disponibile nello storico.";
  return "Stato calcolato dai file presenti e dalla data di scadenza.";
}


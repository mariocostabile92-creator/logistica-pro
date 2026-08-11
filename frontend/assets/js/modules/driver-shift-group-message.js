const MONTHS_IT = Object.freeze([
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]);


function localDate(value) {
  const [year, month, day] = String(value || "").split("-").map(Number);
  const parsed = new Date(year, month - 1, day, 12, 0, 0);
  if (!year || !month || !day || Number.isNaN(parsed.getTime())) {
    throw new Error("DRIVER_SHIFT_GROUP_PERIOD_INVALID");
  }
  return parsed;
}


export function formatGroupMessageDate(value) {
  const parsed = localDate(value);
  return `${parsed.getDate()} ${MONTHS_IT[parsed.getMonth()]} ${parsed.getFullYear()}`;
}


export function buildDriverShiftGroupMessage({
  periodStart,
  periodEnd,
  sharedPortalUrl,
}) {
  const url = String(sharedPortalUrl || "").trim();
  if (!url) throw new Error("DRIVER_SHIFT_GROUP_PORTAL_MISSING");
  return [
    "Ciao a tutti 👋",
    "",
    `Sono disponibili i turni dal ${formatGroupMessageDate(periodStart)} al ${formatGroupMessageDate(periodEnd)}.`,
    "",
    "Apri il link qui sotto e accedi con il tuo Codice Accesso e PIN personale per vedere esclusivamente i tuoi turni:",
    "",
    url,
    "",
    "Ricordati di premere “Ho visto i turni” dopo averli controllati.",
  ].join("\n");
}


export async function copyGroupMessage(text, clipboard = navigator.clipboard) {
  if (!clipboard?.writeText) return false;
  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

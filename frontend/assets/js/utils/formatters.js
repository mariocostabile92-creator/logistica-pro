export function labelForField(field) {
  const labels = {
    driver_name: "driver",
    second_driver_name: "secondo driver",
    vehicle_plate: "targa",
    status: "stato mezzo",
    station: "station/deposito",
    workshop: "officina",
    notes: "note",
    key_available: "chiave",
    fuel_card: "carta carburante",
    vehicle_model: "modello mezzo",
    expirations: "scadenze",
    route: "rotta",
    cycle: "ciclo",
  };
  return labels[field] || "da confermare";
}


export function severityLabel(severity) {
  if (severity === "critical") return "Critico";
  if (severity === "warning") return "Avviso";
  return "Info";
}


const OPERATIONAL_CODE_LABELS = {
  DRIVER_MISSING: "Risorsa non assegnata",
  DRIVER_ALREADY_ASSIGNED: "Risorsa già assegnata",
  DUPLICATE_DRIVER_SOURCE: "Risorsa duplicata nei dati di origine",
  IMPORTED_VEHICLE_INVALID: "Asset importato non valido",
  HABITUAL_VEHICLE_UNAVAILABLE: "Asset abituale non disponibile",
  RESERVE_VEHICLE_USED: "Asset di riserva utilizzato",
  VEHICLE_MISSING: "Asset non assegnato",
  VEHICLE_ALREADY_ASSIGNED: "Asset già assegnato",
  DRIVER_ABSENT_REPLACED: "Risorsa assente sostituita",
  DRIVER_ABSENT_NO_REPLACEMENT: "Risorsa assente senza sostituzione",
  VEHICLE_KO_REPLACED: "Asset non disponibile sostituito",
  VEHICLE_KO_NO_REPLACEMENT: "Asset non disponibile senza sostituzione",
  ROUTE_ABORTED: "Task annullato",
  LOW_RESERVE_MARGIN: "Margine di riserva ridotto",
};


const ASSET_VALUE_LABELS = {
  active: "Attivo",
  inactive: "Inattivo",
  light_van: "Furgone leggero",
  electric: "Elettrico",
  refrigerated: "Refrigerato",
  large_capacity: "Grande capacità",
  special_license_required: "Patente speciale richiesta",
};


function readableIdentifier(value) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return "";
  const words = normalized.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}


export function operationalCodeLabel(value) {
  const normalized = String(value ?? "").trim();
  return OPERATIONAL_CODE_LABELS[normalized] || readableIdentifier(normalized);
}


export function assetValueLabel(value) {
  const normalized = String(value ?? "").trim();
  return ASSET_VALUE_LABELS[normalized] || readableIdentifier(normalized);
}


export function readinessLabel(status) {
  if (status === "green") return "Pronta";
  if (status === "yellow") return "Attenzione";
  if (status === "red") return "Critica";
  return "Non calcolata";
}


export function riskLabel(risk) {
  if (risk === "low") return "Rischio basso";
  if (risk === "medium") return "Rischio medio";
  if (risk === "high") return "Rischio alto";
  return "Rischio non disponibile";
}


export function signedNumber(value) {
  const number = Number(value || 0);
  return number > 0 ? `+${number}` : String(number);
}

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

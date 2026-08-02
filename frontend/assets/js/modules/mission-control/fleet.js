import { setText } from "./dom.js";


export function renderFleet(view) {
  const values = view.fleet || {};
  const fallback = view.loading ? "—" : "Non disponibile";
  [
    ["operationsHomeFleetAvailable", values.available],
    ["operationsHomeFleetUnavailable", values.unavailable],
    ["operationsHomeFleetMaintenance", values.maintenance],
    ["operationsHomeFleetDamage", values.openDamage],
    ["operationsHomeFleetDocuments", values.criticalDocuments],
    ["operationsHomeFleetJournal", values.missingJournal],
    ["operationsHomeFleetDeadlines", values.deadlines],
  ].forEach(([id, value]) => setText(id, Number.isFinite(value) ? value : fallback));
}

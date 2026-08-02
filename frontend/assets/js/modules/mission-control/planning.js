import { setText } from "./dom.js";


const STATUS = { draft: "Bozza", generated: "Bozza", partially_assigned: "In completamento", critical: "In completamento", ready: "Pronto", confirmed: "Confermato", published: "Pubblicato" };


export function renderPlanning(view) {
  const planning = view.planning;
  const fallback = view.loading ? "—" : "Non disponibile";
  setText("operationsHomePlanningDrivers", planning?.driversAssigned ?? fallback);
  setText("operationsHomePlanningVehicles", planning?.vehiclesAssigned ?? fallback);
  setText("operationsHomePlanningConflicts", planning?.conflicts ?? fallback);
  setText("operationsHomePlanningPublication", planning ? (STATUS[planning.publication] || planning.publication) : fallback);
}

import { setText } from "./dom.js";


export function renderWorkforce(view) {
  setText("operationsHomeWorkforceStatus", view.workforce.status);
  document.getElementById("operationsHomeWorkforceFacts").hidden = !view.workforce.available;
  if (!view.workforce.available) return;
  setText("operationsHomeWorkforceDrivers", view.workforce.drivers);
  setText("operationsHomeWorkforceRequired", view.workforce.required);
  setText("operationsHomeWorkforceAbsences", view.workforce.absences);
}

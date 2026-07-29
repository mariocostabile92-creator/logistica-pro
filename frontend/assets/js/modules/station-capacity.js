import { capacityCard } from "../components/capacity-card.js";
import { byId } from "../utils/dom.js";


export function renderStationCapacity(capacities) {
  byId("stationCapacity").innerHTML = capacities.length
    ? capacities.map(capacityCard).join("")
    : '<div class="empty-state">Nessuna capacità station disponibile.</div>';
}

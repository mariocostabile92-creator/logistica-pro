import { loadFleetVisionExcellence } from "./fleet-vision/aggregator.js";
import { openFleetVisionSource } from "./fleet-vision/navigation.js";
import { renderFleetVisionExcellence } from "./fleet-vision/renderer.js";
import {
  fleetVisionState, resetFleetVisionState,
} from "./fleet-vision/state.js";

const root = () => document.getElementById("fleetVisionWorkspace");
const hiddenWorkspaces = "#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace,#deadlinesWorkspace,#journalControlRoom";

function rerender() {
  renderFleetVisionExcellence(root());
}

export async function showFleetVisionWorkspace(options = {}) {
  document.querySelectorAll(hiddenWorkspaces).forEach(element => { element.hidden = true; });
  root().hidden = false;
  root().innerHTML = `<div class="view-state"><strong>Fleet Vision in caricamento</strong>
    <p>Correlazione dei dati operativi in corso.</p></div>`;
  resetFleetVisionState(await loadFleetVisionExcellence(options));
  rerender();
}

document.addEventListener("click", event => {
  if (!event.target.closest("#fleetVisionWorkspace")) return;
  const filter = event.target.closest("[data-fve-filter]")?.dataset.fveFilter;
  if (filter) { fleetVisionState.filter = filter; rerender(); return; }
  const group = event.target.closest("[data-fve-group]")?.dataset.fveGroup;
  if (group) {
    fleetVisionState.expandedGroups.has(group)
      ? fleetVisionState.expandedGroups.delete(group)
      : fleetVisionState.expandedGroups.add(group);
    rerender(); return;
  }
  const vehicle = Number(event.target.closest("[data-fve-vehicle-toggle]")?.dataset.fveVehicleToggle);
  if (vehicle) {
    fleetVisionState.expandedVehicles.has(vehicle)
      ? fleetVisionState.expandedVehicles.delete(vehicle)
      : fleetVisionState.expandedVehicles.add(vehicle);
    rerender(); return;
  }
  const showAll = event.target.closest("[data-fve-show-all]")?.dataset.fveShowAll;
  if (showAll) { fleetVisionState.showAll.add(showAll); rerender(); return; }
  const source = event.target.closest("[data-fve-source]");
  if (source) openFleetVisionSource(
    source.dataset.fveSource,
    Number(source.dataset.fveVehicleId) || fleetVisionState.data.items[0]?.id,
    source.dataset.fveRecordId || null,
  );
});

export const fleetVisionState = {
  data: null,
  filter: "all",
  expandedGroups: new Set(),
  expandedVehicles: new Set(),
  showAll: new Set(),
};

export function resetFleetVisionState(data) {
  fleetVisionState.data = data;
  fleetVisionState.filter = "all";
  fleetVisionState.expandedGroups = new Set(["alta"]);
  fleetVisionState.expandedVehicles = new Set();
  fleetVisionState.showAll = new Set();
}

export function filteredCriticalities() {
  const filter = fleetVisionState.filter;
  return fleetVisionState.data.criticalities.filter(item => {
    if (filter === "all") return true;
    if (filter === "alta") return item.priority === "alta";
    if (filter === "availability") return item.rule === "vehicle_not_operational";
    if (filter === "journal") return item.module === "journal";
    return item.module === filter;
  });
}

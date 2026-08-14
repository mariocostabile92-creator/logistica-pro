export const planningOperationsState = {
  payload: null,
  selectedOperationalDate: null,
  weekPayloads: new Map(),
  weekLoading: false,
  weekError: null,
  query: "",
  filter: "all",
};

export function filteredRoutes(state = planningOperationsState) {
  const routes = state.payload?.routes || [];
  const query = state.query.trim().toLocaleLowerCase("it");
  return routes.filter((route) => {
    const searchable = [route.route_id, route.driver_name, route.plate, route.cycle_or_wave]
      .filter(Boolean).join(" ").toLocaleLowerCase("it");
    if (query && !searchable.includes(query)) return false;
    if (state.filter === "missing-driver") return !route.driver_id;
    if (state.filter === "missing-vehicle") return !route.plate;
    if (state.filter === "conflict") return route.conflicts?.length > 0;
    if (state.filter === "complete") return route.complete;
    if (state.filter === "convocation") return route.convocation?.status === "da_preparare";
    return true;
  }).sort((left, right) => {
    const leftBlocking = left.conflicts?.some((item) => item.blocking || item.severity === "critical");
    const rightBlocking = right.conflicts?.some((item) => item.blocking || item.severity === "critical");
    return Number(rightBlocking) - Number(leftBlocking)
      || Number(left.complete) - Number(right.complete)
      || String(left.cycle_or_wave || "").localeCompare(String(right.cycle_or_wave || ""));
  });
}

export const EMPTY_FILTERS = Object.freeze({
  query: "", callability: "all", availability: "all",
  role: "all", station: "all", contract: "all", reserve: false,
});

export function createAvailabilityState() {
  return { snapshot: null, filters: { ...EMPTY_FILTERS } };
}

export function reduceAvailabilityState(state, event) {
  if (event.type === "snapshot") return { ...state, snapshot: event.value };
  if (event.type === "filter") return { ...state, filters: { ...state.filters, [event.name]: event.value } };
  if (event.type === "reset") return { ...state, filters: { ...EMPTY_FILTERS } };
  if (event.type === "kpi") return { ...state, filters: { ...EMPTY_FILTERS, ...event.filters } };
  return state;
}

export function selectAvailabilityDrivers(state) {
  const filters = state.filters;
  const query = filters.query.trim().toLocaleLowerCase("it");
  return (state.snapshot?.drivers || []).filter((driver) => {
    const searchable = [
      driver.display_name, driver.external_identifier, driver.role,
      driver.station, driver.contract, driver.callability_reason,
      ...(driver.capabilities || []),
    ].filter(Boolean).join(" ").toLocaleLowerCase("it");
    const callability = filters.callability === "all"
      || (filters.callability === "callable_any" && driver.callable)
      || driver.callability_status === filters.callability;
    const availability = filters.availability === "all"
      || (filters.availability === "available" && ["available", "scheduled", "available_limited"].includes(driver.availability_status))
      || driver.availability_status === filters.availability;
    return (!query || searchable.includes(query)) && callability && availability
      && (filters.role === "all" || driver.role === filters.role)
      && (filters.station === "all" || driver.station === filters.station)
      && (filters.contract === "all" || driver.contract === filters.contract)
      && (!filters.reserve || driver.is_reserve);
  });
}

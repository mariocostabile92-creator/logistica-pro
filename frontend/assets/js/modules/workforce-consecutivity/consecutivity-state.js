export const CONSECUTIVITY_FILTERS = Object.freeze({
  consecutivity: "all", consecutiveMin: "", consecutiveMax: "", overrideOnly: false,
});

export function matchesConsecutivity(driver, filters) {
  const item = driver.consecutivity || {};
  const status = item.calculated_status || "dati_insufficienti";
  const count = item.planned_consecutive_days ?? item.effective_consecutive_days;
  if (filters.consecutivity !== "all" && status !== filters.consecutivity) return false;
  if (filters.consecutiveMin !== "" && (count == null || count < Number(filters.consecutiveMin))) return false;
  if (filters.consecutiveMax !== "" && (count == null || count > Number(filters.consecutiveMax))) return false;
  if (filters.overrideOnly && !item.override) return false;
  return true;
}

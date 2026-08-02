export const CONSECUTIVITY_BINDINGS = Object.freeze({
  workforceConsecutivityFilter: "consecutivity",
  workforceConsecutiveMin: "consecutiveMin",
  workforceConsecutiveMax: "consecutiveMax",
  workforceOverrideFilter: "overrideOnly",
});

export function filterValue(element) {
  return element.type === "checkbox" ? element.checked : element.value;
}

export function resetConsecutivityFilters() {
  document.getElementById("workforceConsecutivityFilter").value = "all";
  document.getElementById("workforceConsecutiveMin").value = "";
  document.getElementById("workforceConsecutiveMax").value = "";
  document.getElementById("workforceOverrideFilter").checked = false;
}

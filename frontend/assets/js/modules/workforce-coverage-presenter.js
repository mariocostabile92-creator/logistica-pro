const BUCKETS = Object.freeze([
  { key: "NEXT_DAY", cycle: "NEXT_DAY", segment: null, label: "NEXT DAY" },
  { key: "SAME_DAY_A", cycle: "SAME_DAY", segment: "A", label: "SAME DAY A" },
  { key: "SAME_DAY_B_C", cycle: "SAME_DAY", segment: "B_C", label: "SAME DAY B-C" },
]);

const STATUS_LABELS = Object.freeze({
  UNDER_FORECAST: "Sotto forecast",
  FORECAST_COVERED: "Forecast coperto · manca requisito +10%",
  REQUIREMENT_COVERED: "Requirement coperto",
  NO_FORECAST: "Forecast non disponibile",
});


function addDays(value, amount) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}


export function planningCoverageDates(dateFrom, dateTo = "") {
  if (!dateFrom) return [];
  const dates = [];
  for (let offset = 0; offset < 7; offset += 1) {
    const value = addDays(dateFrom, offset);
    if (dateTo && value > dateTo) break;
    dates.push(value);
  }
  return dates;
}


export function planningCoverageBucketKey(item) {
  if (item?.cycle === "NEXT_DAY") return "NEXT_DAY";
  if (item?.cycle === "SAME_DAY" && item?.segment === "A") return "SAME_DAY_A";
  if (item?.cycle === "SAME_DAY" && item?.segment === "B_C") return "SAME_DAY_B_C";
  return null;
}


export function planningCoverageStatusLabel(status) {
  return STATUS_LABELS[status] || "Stato copertura non disponibile";
}


export function planningCoveragePrimaryMessage(item) {
  if (!item || item.coverage_status === "NO_FORECAST") return "Forecast non disponibile";
  if (Number(item.requirement_gap) > 0) {
    return item.coverage_status === "FORECAST_COVERED"
      ? `Mancano ${item.requirement_gap} al +10%`
      : `Mancano ${item.requirement_gap}`;
  }
  const reserve = Number(item.reserve_drivers) || 0;
  return reserve > 0
    ? `✓ Copertura completata · +${reserve} scorte`
    : "✓ Copertura completata";
}


export function planningCoverageDetails(item) {
  if (!item || item.coverage_status === "NO_FORECAST") {
    return item?.assigned_drivers > 0 ? `${item.assigned_drivers} assegnati` : "Nessun dato forecast";
  }
  if (item.coverage_status === "UNDER_FORECAST") {
    return `${item.forecast_gap} sotto forecast · ${item.requirement_gap} sotto requirement`;
  }
  if (item.coverage_status === "FORECAST_COVERED") return "Forecast coperto";
  return Number(item.reserve_drivers) > 0 ? `+${item.reserve_drivers} scorte` : "Requirement raggiunto";
}


export function planningCoverageDays(response) {
  if (!response) return [];
  const byKey = new Map((response.items || []).map((item) => [
    `${item.operational_date}:${planningCoverageBucketKey(item)}`,
    item,
  ]));
  return planningCoverageDates(response.date_from, response.date_to).map((date) => ({
    date,
    buckets: BUCKETS.map((bucket) => ({
      ...bucket,
      item: byKey.get(`${date}:${bucket.key}`) || null,
    })),
  }));
}


export function planningCoverageWeeklySummary(response) {
  const grouped = new Map(BUCKETS.map((bucket) => [bucket.key, {
    ...bucket,
    forecast: 0,
    requirement: 0,
    assigned: 0,
    forecastAvailable: false,
  }]));
  (response?.items || []).forEach((item) => {
    const summary = grouped.get(planningCoverageBucketKey(item));
    if (!summary) return;
    summary.assigned += Number(item.assigned_drivers) || 0;
    if (item.forecast_routes === null || item.forecast_routes === undefined) return;
    summary.forecastAvailable = true;
    summary.forecast += Number(item.forecast_routes) || 0;
    summary.requirement += Number(item.required_capacity) || 0;
  });
  return [...grouped.values()];
}


export function planningCoverageBucketDefinitions() {
  return BUCKETS.map((bucket) => ({ ...bucket }));
}

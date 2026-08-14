export function renderKpis(summary, fleetCapacity = null) {
  const kpis = [
    [summary.routes_forecast, "Forecast Amazon", null],
    [summary.requirement, "Requirement +10%", null],
    [summary.drivers_planned, "Driver pianificati", null],
    [fleetCapacity?.vehicle_need, "Mezzi necessari", null],
    [fleetCapacity?.available_vehicles, "Mezzi disponibili", null],
    [summary.routes_definitive, "Rotte definitive", "all"],
    [summary.vehicles_assigned, "Mezzi assegnati", "missing-vehicle"],
    [summary.requirement_gap, "Gap requirement", null],
    [summary.conflicts, "Conflitti", "conflict"],
  ];
  return `<section class="planning-ops-kpis" aria-label="Indicatori della giornata">${kpis.map(([rawValue, label, filter]) => {
    const value = rawValue ?? "—";
    return filter
      ? `<button type="button" data-planning-filter="${filter}"><strong>${value}</strong><span>${label}</span></button>`
      : `<article><strong>${value}</strong><span>${label}</span></article>`;
  }).join("")}</section>`;
}

const KPI = [
  ["routes_forecast", "Forecast Amazon", null],
  ["requirement", "Requirement +10%", null],
  ["drivers_planned", "Driver pianificati", null],
  ["routes_definitive", "Rotte definitive", "all"],
  ["vehicles_assigned", "Mezzi assegnati", "missing-vehicle"],
  ["requirement_gap", "Gap requirement", null],
  ["conflicts", "Conflitti", "conflict"],
];

export function renderKpis(summary) {
  return `<section class="planning-ops-kpis" aria-label="Indicatori del piano">${KPI.map(([key, label, filter]) => {
    const value = summary[key] ?? "—";
    return filter
      ? `<button type="button" data-planning-filter="${filter}"><strong>${value}</strong><span>${label}</span></button>`
      : `<article><strong>${value}</strong><span>${label}</span></article>`;
  }).join("")}</section>`;
}

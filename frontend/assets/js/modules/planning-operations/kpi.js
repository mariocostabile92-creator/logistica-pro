const KPI = [
  ["routes_forecast", "Rotte previste", "all"],
  ["routes_definitive", "Rotte definitive", "all"],
  ["drivers_assigned", "Driver assegnati", "missing-driver"],
  ["vehicles_assigned", "Mezzi assegnati", "missing-vehicle"],
  ["routes_complete", "Rotte complete", "complete"],
  ["routes_incomplete", "Da completare", "missing-driver"],
  ["conflicts", "Conflitti", "conflict"],
  ["convocations_ready", "Convocazioni pronte", "convocation"],
];

export function renderKpis(summary) {
  return `<section class="planning-ops-kpis" aria-label="Indicatori del piano">${KPI.map(([key, label, filter]) => `
    <button type="button" data-planning-filter="${filter}"><strong>${summary[key] ?? 0}</strong><span>${label}</span></button>`).join("")}</section>`;
}

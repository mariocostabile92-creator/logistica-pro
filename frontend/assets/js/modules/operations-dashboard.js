import { getOperationsDashboard } from "../api.js";
import { state } from "../state.js";
import { byId, escapeHtml, setLoading, setMessage, setText } from "../utils/dom.js";
import { readinessLabel, riskLabel, signedNumber } from "../utils/formatters.js";
import { renderOperationalIssues } from "./conflicts.js";


function dashboardDetail(card, data) {
  const { summary, capacity, readiness } = data;
  const details = {
    routes: `${summary.routes} rotte previste con ${summary.operational_vehicles} mezzi operativi disponibili.`,
    drivers: `${summary.drivers} driver riconosciuti per ${summary.routes} rotte. Margine driver: ${signedNumber(capacity.driver_margin)}.`,
    vehicles: `${summary.physical_vehicles} mezzi fisici, ${summary.operational_vehicles} operativi e ${summary.blocked_vehicles} bloccati.`,
    readiness: readiness.reasons.join(" "),
  };
  return details[card] || "";
}


function selectDashboardCard(card) {
  const data = state.dashboard.data;
  if (!data) return;
  document.querySelectorAll("[data-dashboard-card]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.dashboardCard === card));
  });
  const detail = byId("metricDetail");
  detail.textContent = dashboardDetail(card, data);
  detail.focus({ preventScroll: true });
}


function renderReadiness(readiness) {
  const card = byId("readinessCard");
  card.className = `readiness-card ${readiness.status}`;
  setText("readinessTitle", readinessLabel(readiness.status));
  setText("readinessRisk", riskLabel(readiness.risk_level));
  setText("readinessMargin", `Margine ${signedNumber(readiness.operational_margin)}`);
  byId("readinessReasons").innerHTML = readiness.reasons
    .map((reason) => `<p>${escapeHtml(reason)}</p>`)
    .join("");
}


function renderDashboard(data) {
  state.dashboard.data = data;
  const { summary, capacity, readiness, issues } = data;
  setText("routesValue", summary.routes);
  setText("routesMeta", `${summary.critical_issues} criticità`);
  setText("driversValue", summary.drivers);
  setText("driversMeta", `${signedNumber(capacity.driver_margin)} rispetto alle rotte`);
  setText("vehiclesValue", summary.operational_vehicles);
  setText("vehiclesMeta", `${summary.physical_vehicles} fisici · ${summary.blocked_vehicles} bloccati`);
  setText("physicalVehiclesValue", summary.physical_vehicles);
  setText("blockedVehiclesValue", summary.blocked_vehicles);
  setText("reserveVehiclesValue", summary.reserve_vehicles);
  setText("issuesCount", summary.issues_count);
  setText(
    "dashboardTimestamp",
    `Aggiornato ${new Date(data.generated_at).toLocaleString("it-IT")}`,
  );
  renderReadiness(readiness);
  renderOperationalIssues(byId("conflicts"), issues);
  byId("metricDetail").textContent = dashboardDetail("readiness", data);
}


async function loadDashboard({ quiet = false } = {}) {
  const button = byId("analyzeBtn");
  if (!quiet) setLoading(button, true, "Calcolo...");
  try {
    const threshold = Number(byId("reserveThreshold").value || 0);
    const data = await getOperationsDashboard(threshold);
    renderDashboard(data);
    setMessage("");
  } catch (error) {
    setText("dashboardTimestamp", error.message);
    if (!quiet) setMessage(error.message);
  } finally {
    if (!quiet) setLoading(button, false);
  }
}


export function initOperationsDashboard() {
  byId("analyzeBtn").addEventListener("click", () => loadDashboard());
  document.querySelectorAll("[data-dashboard-card]").forEach((button) => {
    button.addEventListener("click", () => selectDashboardCard(button.dataset.dashboardCard));
  });
  document.addEventListener("operations:data-imported", () => {
    setText("dashboardTimestamp", "Dati aggiornati. Lo stato operativo deve essere ricalcolato.");
  });
  loadDashboard({ quiet: true });
}

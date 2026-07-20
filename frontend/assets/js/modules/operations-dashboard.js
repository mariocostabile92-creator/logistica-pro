import { getOperationsDashboard } from "../api.js";
import { state } from "../state.js";
import {
  byId,
  escapeHtml,
  renderViewState,
  setLoading,
  setMessage,
  setText,
  showDataView,
} from "../utils/dom.js";
import {
  isExpectedApiError,
  reportUnexpectedError,
} from "../utils/errors.js";
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
  showDataView("dashboardViewState", "dashboardDataView", true);
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
  document.dispatchEvent(new CustomEvent("operations:dashboard-updated", {
    detail: { available: true },
  }));
}


function renderDashboardLoading() {
  state.dashboard.data = null;
  showDataView("dashboardViewState", "dashboardDataView", false);
  setText("dashboardTimestamp", "Caricamento dello stato operativo...");
  renderViewState(byId("dashboardViewState"), {
    state: "loading",
    title: "Caricamento stato operativo",
  });
}


function renderDashboardEmpty({
  title = "Nessun planning disponibile.",
  description = "Importa il primo file per iniziare.",
  actionLabel = "Vai alle importazioni",
  action = "open-imports",
} = {}) {
  state.dashboard.data = null;
  showDataView("dashboardViewState", "dashboardDataView", false);
  setText("dashboardTimestamp", "Dashboard: nessun dato.");
  renderViewState(byId("dashboardViewState"), {
    state: "empty",
    title,
    description,
    actionLabel,
    action,
  });
  document.dispatchEvent(new CustomEvent("operations:dashboard-updated", {
    detail: { available: false },
  }));
}


function renderDashboardFailure() {
  state.dashboard.data = null;
  showDataView("dashboardViewState", "dashboardDataView", false);
  setText("dashboardTimestamp", "Stato operativo non disponibile.");
  renderViewState(byId("dashboardViewState"), {
    state: "error",
    title: "Impossibile caricare la dashboard",
    description: "Il servizio non ha completato il caricamento. Riprova tra poco.",
    actionLabel: "Riprova",
    action: "retry-dashboard",
  });
  document.dispatchEvent(new CustomEvent("operations:dashboard-updated", {
    detail: { available: false },
  }));
}


async function loadDashboard({ quiet = false } = {}) {
  const button = byId("analyzeBtn");
  if (!quiet) setLoading(button, true, "Calcolo...");
  renderDashboardLoading();
  try {
    const threshold = Number(byId("reserveThreshold").value || 0);
    const data = await getOperationsDashboard(threshold);
    renderDashboard(data);
    setMessage("");
  } catch (error) {
    if (isExpectedApiError(error, {
      statuses: [400],
      messages: ["Nessun planning importato", "Nessun parco auto importato"],
    })) {
      renderDashboardEmpty();
      return;
    }
    reportUnexpectedError("operations.dashboard", error);
    renderDashboardFailure();
  } finally {
    if (!quiet) setLoading(button, false);
  }
}


export function initOperationsDashboard() {
  byId("analyzeBtn").addEventListener("click", () => loadDashboard());
  byId("dashboardViewState").addEventListener("click", (event) => {
    const action = event.target.closest("[data-view-action]")?.dataset.viewAction;
    if (action === "retry-dashboard" || action === "calculate-dashboard") {
      loadDashboard();
    }
    if (action === "open-imports") {
      byId("importsSection").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  document.querySelectorAll("[data-dashboard-card]").forEach((button) => {
    button.addEventListener("click", () => selectDashboardCard(button.dataset.dashboardCard));
  });
  document.addEventListener("operations:data-imported", () => {
    renderDashboardEmpty({
      title: "Dati aggiornati",
      description: "Calcola lo stato operativo per aggiornare readiness e criticità.",
      actionLabel: "Calcola stato operativo",
      action: "calculate-dashboard",
    });
  });
  document.addEventListener("planning:availability-changed", (event) => {
    if (event.detail.hasPlanning) {
      loadDashboard({ quiet: true });
      return;
    }
    if (event.detail.failed) {
      renderDashboardEmpty({
        title: "Planning non disponibile",
        description: "La dashboard sarà disponibile quando il planning sarà nuovamente raggiungibile.",
      });
      return;
    }
    renderDashboardEmpty();
  });
  document.addEventListener("demo:workspace-changed", () => {
    loadDashboard({ quiet: true });
  });
  renderDashboardLoading();
}

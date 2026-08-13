import { getPlanningCoverage } from "../api.js?v=21";
import { escapeHtml } from "../utils/dom.js";
import {
  completePlanningCoverageLoad,
  createPlanningCoverageState,
  failPlanningCoverageLoad,
  startPlanningCoverageLoad,
} from "./workforce-coverage-state.js";
import {
  planningCoverageDays,
  planningCoverageDetails,
  planningCoveragePrimaryMessage,
  planningCoverageStatusLabel,
  planningCoverageWeeklySummary,
} from "./workforce-coverage-presenter.js";


function shortDay(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "short",
    day: "2-digit",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


function metric(label, value) {
  return `<span><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b></span>`;
}


function renderBucket(bucket, cycleFilter) {
  const item = bucket.item;
  const isDimmed = cycleFilter !== "all" && cycleFilter !== bucket.cycle;
  const status = item?.coverage_status || "NO_FORECAST";
  const forecast = item?.forecast_routes ?? "—";
  const requirement = item?.required_capacity ?? "—";
  const assigned = item?.assigned_drivers ?? 0;
  return `
    <section class="planning-coverage-bucket is-${status.toLowerCase().replaceAll("_", "-")}${isDimmed ? " is-dimmed" : ""}" data-coverage-bucket="${bucket.key}">
      <div class="planning-coverage-bucket-heading">
        <strong>${escapeHtml(bucket.label)}</strong>
        <span>${escapeHtml(planningCoverageStatusLabel(status))}</span>
      </div>
      <div class="planning-coverage-metrics">
        ${metric("Forecast", forecast)}
        ${metric("Requirement +10%", requirement)}
        ${metric("Assegnati", assigned)}
      </div>
      <b class="planning-coverage-primary">${escapeHtml(planningCoveragePrimaryMessage(item))}</b>
      <small class="planning-coverage-detail">${escapeHtml(planningCoverageDetails(item))}</small>
    </section>
  `;
}


function renderSummary(response) {
  return planningCoverageWeeklySummary(response).map((item) => `
    <section class="planning-coverage-summary-item" data-coverage-summary="${item.key}">
      <strong>${escapeHtml(item.label)}</strong>
      <span>Forecast settimana: <b>${item.forecastAvailable ? item.forecast : "Non disponibile"}</b></span>
      <span>Requirement settimana: <b>${item.forecastAvailable ? item.requirement : "Non disponibile"}</b></span>
      <span>Assegnazioni: <b>${item.assigned}</b></span>
    </section>
  `).join("");
}


function renderBoard(container, liveRegion, state) {
  container.classList.toggle("is-loading", state.coverageLoading);
  const loading = container.querySelector("[data-coverage-loading]");
  if (loading) loading.hidden = !state.coverageLoading;
  const error = container.querySelector("[data-coverage-error]");
  if (error) {
    error.hidden = !state.coverageError;
    error.textContent = state.coverageError ? "Impossibile aggiornare la copertura." : "";
  }
  if (!state.coverageData) return;
  const days = container.querySelector("[data-coverage-days]");
  days.innerHTML = planningCoverageDays(state.coverageData).map((day) => `
    <article class="planning-coverage-day${day.date === state.coverageFocusedDate ? " is-focused" : ""}" data-coverage-day="${day.date}">
      <button type="button" class="planning-coverage-day-focus" data-coverage-date="${day.date}" aria-pressed="${day.date === state.coverageFocusedDate}">
        <span>${escapeHtml(shortDay(day.date))}</span><small>${escapeHtml(day.date)}</small>
      </button>
      ${day.buckets.map((bucket) => renderBucket(bucket, state.coverageCycleFilter)).join("")}
    </article>
  `).join("");
  container.querySelector("[data-coverage-summary]").innerHTML = renderSummary(state.coverageData);
  if (state.coverageLastUpdated) {
    const time = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
      .format(state.coverageLastUpdated);
    container.querySelector("[data-coverage-updated]").textContent = `Aggiornata alle ${time}`;
  }
  if (liveRegion && !state.coverageLoading) {
    liveRegion.textContent = state.coverageError
      ? "Impossibile aggiornare la copertura."
      : "Copertura aggiornata.";
  }
}


export function createPlanningCoverageBoard({
  container,
  liveRegion,
  fetchCoverage = getPlanningCoverage,
  onDayFocus = () => {},
  onCoverageChange = () => {},
}) {
  let state = createPlanningCoverageState();
  let dateFrom = "";
  let dateTo = "";
  let requestSequence = 0;

  const render = () => renderBoard(container, liveRegion, state);

  async function load(nextDateFrom = dateFrom, nextDateTo = dateTo) {
    if (!nextDateFrom || !nextDateTo) return null;
    dateFrom = nextDateFrom;
    dateTo = nextDateTo;
    const sequence = ++requestSequence;
    state = startPlanningCoverageLoad(state);
    render();
    try {
      const response = await fetchCoverage(dateFrom, dateTo);
      if (sequence !== requestSequence) return null;
      state = completePlanningCoverageLoad(state, response);
      if (!state.coverageFocusedDate || state.coverageFocusedDate < dateFrom || state.coverageFocusedDate > dateTo) {
        state.coverageFocusedDate = dateFrom;
      }
      render();
      onCoverageChange(response);
      return response;
    } catch (error) {
      if (sequence !== requestSequence) return null;
      state = failPlanningCoverageLoad(state, error);
      render();
      onCoverageChange(null);
      return null;
    }
  }

  function setCycleFilter(cycle) {
    state.coverageCycleFilter = ["NEXT_DAY", "SAME_DAY"].includes(cycle) ? cycle : "all";
    render();
  }

  function focusDate(date, { notify = false } = {}) {
    if (!date || date < dateFrom || date > dateTo) return;
    state.coverageFocusedDate = date;
    render();
    if (notify) onDayFocus(date);
  }

  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-coverage-date]");
    if (!button) return;
    focusDate(button.dataset.coverageDate, { notify: true });
  });

  render();
  return {
    load,
    refresh: () => load(dateFrom, dateTo),
    setCycleFilter,
    focusDate,
    getState: () => ({ ...state }),
  };
}

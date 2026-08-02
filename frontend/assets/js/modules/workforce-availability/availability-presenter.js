import { availabilityCard } from "./availability-card.js";
import { KPI_FILTERS, renderAvailabilityKpis } from "./availability-kpi.js";
import { createAvailabilityState, reduceAvailabilityState, selectAvailabilityDrivers } from "./availability-state.js";
import { createAvailabilityDetail } from "./availability-detail.js";

let state = createAvailabilityState();
let detail = null;
let activeKpi = "";

function options(field) {
  return [...new Set((state.snapshot?.drivers || []).map((item) => item[field]).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "it"));
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  const current = select.value;
  const first = select.options[0];
  select.replaceChildren(first, ...values.map((value) => {
    const option = document.createElement("option"); option.value = value; option.textContent = value; return option;
  }));
  select.value = values.includes(current) ? current : "all";
}

function render() {
  if (!state.snapshot) return;
  const drivers = selectAvailabilityDrivers(state);
  document.getElementById("workforceFoundationDate").textContent = state.snapshot.operation_date;
  document.getElementById("workforceFoundationResultCount").textContent = `${drivers.length} driver`;
  document.getElementById("workforceFoundationLimit").textContent = state.snapshot.limitations[0] || "";
  renderAvailabilityKpis(state.snapshot.summary, activeKpi);
  document.getElementById("workforceFoundationDrivers").innerHTML = drivers.length
    ? drivers.map(availabilityCard).join("")
    : '<p class="workforce-foundation-empty">Nessun driver corrisponde ai filtri.</p>';
}

function setFilter(name, value) {
  activeKpi = "";
  state = reduceAvailabilityState(state, { type: "filter", name, value });
  render();
}

export function initAvailabilityPresenter() {
  detail = createAvailabilityDetail();
  const bindings = {
    workforceFoundationSearch: "query", workforceCallabilityFilter: "callability",
    workforceAvailabilityFilter: "availability", workforceRoleFilter: "role",
    workforceStationFilter: "station", workforceContractFilter: "contract",
  };
  for (const [id, name] of Object.entries(bindings)) {
    const eventName = id === "workforceFoundationSearch" ? "input" : "change";
    document.getElementById(id)?.addEventListener(eventName, (event) => setFilter(name, event.target.value));
  }
  document.getElementById("workforceFoundationReset")?.addEventListener("click", () => {
    activeKpi = ""; state = reduceAvailabilityState(state, { type: "reset" });
    document.getElementById("workforceFoundationSearch").value = "";
    document.querySelectorAll(".workforce-foundation-tools select").forEach((select) => { select.value = "all"; });
    render();
  });
  document.getElementById("workforceFoundationKpis")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-workforce-kpi-filter]");
    if (!button) return;
    activeKpi = button.dataset.workforceKpiFilter;
    state = reduceAvailabilityState(state, { type: "kpi", filters: KPI_FILTERS[activeKpi] });
    render();
  });
  document.getElementById("workforceFoundationDrivers")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-workforce-driver-detail]");
    if (!button) return;
    const driver = state.snapshot.drivers.find((item) => item.workforce_member_id === Number(button.dataset.workforceDriverDetail));
    if (driver) detail.open(driver);
  });
}

export function presentAvailabilitySnapshot(snapshot) {
  state = reduceAvailabilityState(state, { type: "snapshot", value: snapshot });
  fillSelect("workforceRoleFilter", options("role"));
  fillSelect("workforceStationFilter", options("station"));
  fillSelect("workforceContractFilter", options("contract"));
  render();
}

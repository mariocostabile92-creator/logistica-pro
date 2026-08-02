export const KPI_FILTERS = Object.freeze({
  Total: {}, Callable: { callability: "callable_any" },
  Available: { availability: "available" }, Reserves: { reserve: true },
  Holiday: { availability: "holiday" }, Sickness: { availability: "sickness" },
  Leave: { availability: "leave" }, Rest: { availability: "rest" },
  NotCallable: { callability: "not_callable" },
});

export function renderAvailabilityKpis(summary, activeKey = "") {
  for (const [suffix, count] of [
    ["Total", summary.total], ["Callable", summary.callable],
    ["Available", summary.available], ["Reserves", summary.reserves],
    ["Holiday", summary.holiday], ["Sickness", summary.sickness],
    ["Leave", summary.leave], ["Rest", summary.rest],
    ["NotCallable", summary.not_callable],
  ]) {
    const button = document.querySelector(`[data-workforce-kpi-filter="${suffix}"]`);
    if (!button) continue;
    button.querySelector("strong").textContent = count;
    button.classList.toggle("is-active", activeKey === suffix);
    button.setAttribute("aria-pressed", String(activeKey === suffix));
  }
}

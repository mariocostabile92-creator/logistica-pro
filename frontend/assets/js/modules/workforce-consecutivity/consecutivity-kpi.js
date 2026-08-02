export const CONSECUTIVITY_KPI_FILTERS = Object.freeze({
  Total: {}, Callable: { callability: "callable_any" },
  NotCallable: { callability: "not_callable" }, Limited: { callability: "limited" },
  AtLimit: { consecutivity: "limite_raggiunto" },
  RestRecommended: { consecutivity: "riposo_raccomandato" },
  Insufficient: { consecutivity: "dati_insufficienti" },
  Overrides: { overrideOnly: true },
});

export function renderConsecutivityKpis(summary, activeKey = "") {
  const values = {
    Total: summary.total, Callable: summary.callable, NotCallable: summary.not_callable,
    Limited: summary.limited, AtLimit: summary.at_limit,
    RestRecommended: summary.rest_recommended,
    Insufficient: summary.insufficient_data, Overrides: summary.active_overrides,
  };
  Object.entries(values).forEach(([key, value]) => {
    const button = document.querySelector(`[data-workforce-kpi-filter="${key}"]`);
    if (!button) return;
    button.querySelector("strong").textContent = value || 0;
    button.classList.toggle("is-active", activeKey === key);
    button.setAttribute("aria-pressed", String(activeKey === key));
  });
}

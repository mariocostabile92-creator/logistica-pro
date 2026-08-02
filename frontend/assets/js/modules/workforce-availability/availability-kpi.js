import {
  CONSECUTIVITY_KPI_FILTERS,
  renderConsecutivityKpis,
} from "../workforce-consecutivity/consecutivity-kpi.js";

export const KPI_FILTERS = CONSECUTIVITY_KPI_FILTERS;

export function renderAvailabilityKpis(summary, activeKey = "") {
  renderConsecutivityKpis(summary, activeKey);
}

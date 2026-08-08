import { renderForecast } from "./forecast.js";
import { renderHero } from "./hero.js?v=brand1";
import { renderKpis } from "./kpi.js";
import { renderRoutes } from "./routes.js";
import { escapeHtml } from "../../utils/dom.js";
import { planningDriverOptions } from "../workforce-consecutivity/planning-adapter.js";

export function renderOperationsLoading(root) {
  root.innerHTML = `<section class="planning-ops-loading" aria-label="Caricamento Piano operativo">
    <div><p class="eyebrow oe-workspace-brand"><img class="oe-brand-mark" src="/app/assets/brand/operations-engine-mark.png?v=1" width="192" height="134" alt="" aria-hidden="true"><span>Cabina di regia Dispatcher</span></p><h2>Piano operativo</h2><p>Caricamento dei dati principali…</p></div>
    <div class="planning-ops-loading-kpis" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
  </section>`;
}

export function renderOperations(root, payload, routes) {
  const workforce = payload.workforce || { summary: {}, drivers: [], limitations: [] };
  const driverOptions = planningDriverOptions(workforce);
  root.innerHTML = `${renderHero(payload)}${renderKpis(payload.summary)}
    <section class="planning-ops-panel planning-workforce-input"><header><div><p class="eyebrow">Input Workforce</p><h3>Planning Driver</h3></div><strong>${workforce.summary.callable || 0} convocabili · ${workforce.summary.reserves || 0} riserve</strong></header><p>Elenco persone disponibili per ${workforce.operation_date || "la data operativa"}. L'assegnazione resta nel Planning.</p><datalist id="planningWorkforceDrivers">${driverOptions}</datalist></section>
    <section class="planning-ops-toolbar" aria-label="Filtri rotte">
      <label><span>Cerca</span><input type="search" data-planning-query placeholder="Rotta, driver, targa o wave"></label>
      <label><span>Stato</span><select data-planning-filter-select><option value="all">Tutte</option><option value="missing-driver">Senza driver</option><option value="missing-vehicle">Senza mezzo</option><option value="conflict">Con conflitti</option><option value="complete">Complete</option><option value="convocation">Convocazione da preparare</option></select></label>
      <label class="planning-import-trigger">Importa rotte<input type="file" accept=".xlsx,.xls,.csv" data-planning-import-file></label>
      <span data-planning-import-feedback aria-live="polite"></span>
    </section>
    ${renderForecast(payload.forecast, payload.planning?.operation_date, payload.summary.routes_definitive)}
    <section class="planning-ops-panel planning-routes-panel"><header><div><p class="eyebrow">Superficie operativa</p><h3>Rotte definitive</h3></div><span>${routes.length} rotte</span></header><div data-planning-routes>${renderRoutes(routes, payload.permissions.write)}</div></section>
    <section class="planning-ops-panel planning-publication"><header><div><p class="eyebrow">Lifecycle</p><h3>Conferma e pubblicazione</h3></div></header>
      <dl><div><dt>Rotte</dt><dd>${payload.summary.routes_definitive}</dd></div><div><dt>Incomplete</dt><dd>${payload.summary.routes_incomplete}</dd></div><div><dt>Conflitti bloccanti</dt><dd>${payload.summary.blocking_conflicts || 0}</dd></div><div><dt>Convocazioni pronte</dt><dd>${payload.summary.convocations_ready}</dd></div></dl>
      <div><button type="button" data-planning-lifecycle="confirm" ${payload.lifecycle.can_confirm && payload.permissions.write ? "" : "disabled"}>Conferma piano</button><button type="button" data-planning-lifecycle="publish" ${payload.lifecycle.can_publish && payload.permissions.write ? "" : "disabled"}>Pubblica piano</button></div>
    </section>`;
}

export function renderRouteList(root, routes, writable) {
  const target = root.querySelector("[data-planning-routes]");
  if (target) target.innerHTML = renderRoutes(routes, writable);
}

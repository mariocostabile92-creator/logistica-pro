import { renderForecast } from "./forecast.js?v=forecast1";
import { renderHero } from "./hero.js?v=day1";
import { renderKpis } from "./kpi.js";
import { renderRoutes } from "./routes.js";
import {
  formatOperationalDay,
  renderDayNavigation,
  renderWeekSummary,
} from "./day-navigation.js?v=day1";
import { escapeHtml } from "../../utils/dom.js";
import { planningDriverOptions } from "../workforce-consecutivity/planning-adapter.js";

export function renderOperationsLoading(root) {
  root.innerHTML = `<section class="planning-ops-loading" aria-label="Caricamento Piano operativo">
    <div><p class="eyebrow oe-workspace-eyebrow"><img class="oe-workspace-mark" src="/app/assets/brand/operations-engine-mark.png?v=1" width="192" height="134" alt="" aria-hidden="true"><span>Cabina di regia Dispatcher</span></p><h2>Piano operativo</h2><p>Caricamento dei dati principali…</p></div>
    <div class="planning-ops-loading-kpis" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
  </section>`;
}

export function renderOperations(root, payload, routes, dayState = {}) {
  const workforce = payload.workforce || { summary: {}, drivers: [] };
  const summary = workforce.summary || {};
  const driverOptions = planningDriverOptions(workforce);
  const unavailable = (value) => value ?? "—";
  const routesState = payload.route_data_available
    ? renderRoutes(routes, payload.permissions.write)
    : '<p class="planning-ops-empty planning-source-empty"><strong>Rotte definitive non ancora importate</strong><span>Il Forecast Amazon è un conteggio: non genera rotte route-level.</span></p>';
  const routeCount = payload.route_data_available ? `${routes.length} rotte` : "Non disponibili";
  const operationLabel = formatOperationalDay(payload.operation_date);
  root.innerHTML = `${renderDayNavigation(payload.operation_date, dayState.weekPayloads)}${renderHero(payload)}${renderKpis(payload.summary)}
    <section class="planning-ops-panel planning-workforce-input"><header><div><p class="eyebrow">Input Workforce</p><h3>Planning Driver</h3></div><button type="button" class="secondary" data-open-workforce-planning>Apri Planning Workforce</button></header>
      <div class="planning-workforce-summary"><span><strong>${unavailable(summary.planned)}</strong> pianificati</span><span><strong>${unavailable(summary.available)}</strong> disponibili</span><span><strong>${unavailable(summary.absent)}</strong> assenti</span><span><strong>${unavailable(summary.next_day)}</strong> Next Day</span><span><strong>${unavailable(summary.same_day)}</strong> Same Day</span><span><strong>${unavailable(summary.not_set)}</strong> ciclo da definire</span></div>
      <p>Fonte Workforce canonica per ${workforce.operation_date || payload.operation_date}. Coverage ${workforce.coverage?.requirement_covered === true ? "coperta" : workforce.coverage?.available ? "da completare" : "non disponibile"}.</p><datalist id="planningWorkforceDrivers">${driverOptions}</datalist></section>
    <section class="planning-ops-toolbar" aria-label="Filtri rotte">
      <label><span>Cerca</span><input type="search" data-planning-query placeholder="Rotta, driver, targa o wave"></label>
      <label><span>Stato</span><select data-planning-filter-select><option value="all">Tutte</option><option value="missing-driver">Senza driver</option><option value="missing-vehicle">Senza mezzo</option><option value="conflict">Con conflitti</option><option value="complete">Complete</option><option value="convocation">Convocazione da preparare</option></select></label>
      <label class="planning-import-trigger">Importa rotte del ${operationLabel}<input type="file" accept=".xlsx,.xls,.csv" data-planning-import-file></label>
      <span data-planning-import-feedback aria-live="polite"></span>
    </section>
    ${renderForecast(payload.coverage, {
      operationLabel,
      writable: payload.permissions.write,
      editor: dayState.forecastEditor,
    })}
    <section class="planning-ops-panel planning-routes-panel"><header><div><p class="eyebrow">Superficie operativa</p><h3>Rotte definitive</h3></div><span>${routeCount}</span></header><div data-planning-routes>${routesState}</div></section>
    <section class="planning-ops-panel planning-vehicles-state"><header><div><p class="eyebrow">Fleet input</p><h3>Mezzi</h3></div><strong>${payload.vehicle_assignments_available ? `${payload.summary.vehicles_assigned} assegnati` : "Non disponibili"}</strong></header>${payload.vehicle_assignments_available ? "" : '<p class="planning-ops-empty planning-source-empty"><strong>Mezzi non ancora assegnati</strong><span>Le assegnazioni saranno mostrate solo quando esisteranno dati route-level reali.</span></p>'}</section>
    <section class="planning-ops-panel planning-publication"><header><div><p class="eyebrow">Lifecycle</p><h3>Conferma e pubblicazione</h3></div></header>
      <dl><div><dt>Rotte</dt><dd>${unavailable(payload.summary.routes_definitive)}</dd></div><div><dt>Incomplete</dt><dd>${unavailable(payload.summary.routes_incomplete)}</dd></div><div><dt>Conflitti bloccanti</dt><dd>${unavailable(payload.summary.blocking_conflicts)}</dd></div><div><dt>Convocazioni pronte</dt><dd>${unavailable(payload.summary.convocations_ready)}</dd></div></dl>
      <p class="planning-lifecycle-scope">Queste azioni riguardano esclusivamente ${operationLabel}.</p>
      <div><button type="button" data-planning-lifecycle="confirm" ${payload.lifecycle.can_confirm && payload.permissions.write ? "" : "disabled"}>Conferma giornata</button><button type="button" data-planning-lifecycle="publish" ${payload.lifecycle.can_publish && payload.permissions.write ? "" : "disabled"}>Pubblica giornata</button></div>
      ${payload.lifecycle.disabled_reason ? `<p class="planning-lifecycle-reason">${escapeHtml(payload.lifecycle.disabled_reason)}</p>` : ""}
    </section>${renderWeekSummary(payload.operation_date, dayState.weekPayloads, { loading: dayState.weekLoading, error: dayState.weekError })}`;
}

export function renderRouteList(root, routes, writable) {
  const target = root.querySelector("[data-planning-routes]");
  if (target) target.innerHTML = renderRoutes(routes, writable);
}

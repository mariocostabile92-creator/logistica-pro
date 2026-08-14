import { byId, escapeHtml, renderViewState } from "../../utils/dom.js";
import { buildDspRowActions } from "./actions.js";
import {
  orderedSignals,
  partialSourceItems,
  rowTone,
} from "./presentation.js";


const SIGNAL_LABELS = Object.freeze({
  DRIVER_WITHOUT_VEHICLE: "Mezzo non assegnato",
  DRIVER_NOT_AVAILABLE: "Driver non disponibile",
  VEHICLE_NOT_AVAILABLE: "Mezzo non disponibile",
  JOURNAL_CHECKOUT_MISSING: "Presa in carico mancante",
  JOURNAL_CHECKIN_MISSING: "Rientro mancante",
  JOURNAL_ANOMALY: "Anomalia Giornale di bordo",
  JOURNAL_IN_PROGRESS: "Giornale in compilazione",
  OPEN_DAMAGE_CASE: "Pratica danno aperta",
  VEHICLE_BLOCKED_BY_DAMAGE: "Mezzo fermo per danno",
  HIGH_SEVERITY_DAMAGE: "Danno ad alta gravità",
});

const STATUS_LABELS = Object.freeze({
  available: "Disponibile",
  scheduled: "Disponibile",
  available_limited: "Disponibile con limitazioni",
  rest: "Riposo",
  holiday: "Ferie",
  sickness: "Malattia",
  leave: "Permesso",
  unavailable: "Non disponibile",
  unknown: "Da verificare",
  disponibile: "Disponibile",
  disponibile_con_limitazioni: "Disponibile con limitazioni",
  indisponibile: "Non disponibile",
  in_manutenzione: "In manutenzione",
  in_officina: "In officina",
  reserve: "Disponibile con limitazioni",
  maintenance: "In manutenzione",
  workshop: "In officina",
});

const SOURCE_LABELS = Object.freeze({
  LEGACY_OPERATIONAL_PLANNING: "Planning operativo",
  WORKFORCE_OPERATIONAL_PROJECTION: "Workforce operativo",
});

const COVERAGE_STATUS_LABELS = Object.freeze({
  NO_FORECAST: "Forecast non disponibile",
  UNDER_FORECAST: "Sotto forecast",
  FORECAST_COVERED: "Forecast coperto",
  REQUIREMENT_COVERED: "Requisito coperto",
});


export function signalLabel(code) {
  return SIGNAL_LABELS[code] || "Attenzione operativa";
}


function statusLabel(value, fallback = "Da verificare") {
  return STATUS_LABELS[String(value || "").toLowerCase()] || fallback;
}


function driverLabel(row) {
  return row.driver?.name || row.driver?.planning_identifier || "Driver non identificato";
}


function vehicleLabel(row) {
  return row.vehicle?.plate || "Mezzo non assegnato";
}


function signalMarkup(signals) {
  const ordered = orderedSignals(signals);
  if (!ordered.length) return '<span class="dsp-clear-label">Situazione regolare</span>';
  const [primary, ...secondary] = ordered;
  const label = ordered.map((signal) => signalLabel(signal.code)).join(", ");
  const moreLabel = secondary.length === 1 ? "+1 altra" : `+${secondary.length} altre`;
  const moreAria = secondary.length === 1
    ? "Mostra un'altra criticità"
    : `Mostra altre ${secondary.length} criticità`;
  const secondaryMarkup = secondary.map((signal) => `
    <span class="dsp-signal dsp-signal-${escapeHtml(signal.severity)}">
      ${escapeHtml(signalLabel(signal.code))}
    </span>
  `).join("");
  return `
    <div class="dsp-signal-cluster" aria-label="Criticità: ${escapeHtml(label)}">
      <span class="dsp-signal dsp-signal-primary dsp-signal-${escapeHtml(primary.severity)}">
        ${escapeHtml(signalLabel(primary.code))}
      </span>
      ${secondary.length ? `
        <details class="dsp-more-signals">
          <summary aria-label="${moreAria}">${moreLabel}</summary>
          <div>${secondaryMarkup}</div>
        </details>
      ` : ""}
    </div>
  `;
}


function procedureLabel(operation, status) {
  const labels = {
    check_out: {
      completed: "Presa in carico completata",
      missing: "Presa in carico mancante",
      pending: "Presa in carico attesa",
      not_expected: "Presa in carico non prevista",
      unknown: "Presa in carico da verificare",
    },
    check_in: {
      completed: "Rientro completato",
      missing: "Rientro mancante",
      pending: "Rientro atteso",
      not_expected: "Rientro non previsto",
      unknown: "Rientro da verificare",
    },
  };
  return labels[operation]?.[status] || labels[operation].unknown;
}


function journalMarkup(journal = {}, compact = false) {
  if (journal.available === false) {
    return "<strong>Non disponibile</strong><small>La board resta operativa</small>";
  }
  if (journal.partial) {
    return "<strong>Da verificare</strong><small>Correlazione non certa</small>";
  }
  const detail = [
    procedureLabel("check_in", journal.check_in_status),
    journal.anomaly ? "Anomalia presente" : null,
    journal.in_progress ? "Procedura in compilazione" : null,
  ].filter(Boolean).join(" · ");
  if (compact) {
    return `<strong class="dsp-status-line">${escapeHtml([
      procedureLabel("check_out", journal.check_out_status),
      procedureLabel("check_in", journal.check_in_status),
    ].join(" · "))}</strong>`;
  }
  return `
    <strong>${escapeHtml(procedureLabel("check_out", journal.check_out_status))}</strong>
    <small>${escapeHtml(detail)}</small>
  `;
}


function damageMarkup(damage = {}, compact = false) {
  if (damage.available === false) {
    return "<strong>Non disponibile</strong><small>La board resta operativa</small>";
  }
  if (damage.partial && !damage.open_cases_count) {
    return "<strong>Da verificare</strong><small>Correlazione non certa</small>";
  }
  if (!damage.open_cases_count) {
    return compact
      ? '<strong class="dsp-status-line">Nessun danno aperto</strong>'
      : '<strong>Nessuna criticità</strong><small>Nessuna pratica aperta</small>';
  }
  const count = damage.open_cases_count === 1
    ? "1 pratica aperta"
    : `${damage.open_cases_count} pratiche aperte`;
  const detail = [
    damage.vehicle_blocked ? "Mezzo fermo" : null,
    damage.highest_severity ? `Gravità ${damage.highest_severity}` : null,
  ].filter(Boolean).join(" · ");
  return `<strong>${escapeHtml(count)}</strong><small>${escapeHtml(detail)}</small>`;
}


function actionButton(item, assignmentId, primary = false) {
  return `<button type="button" class="${primary ? "primary" : "quiet"}"
    data-dsp-action="${escapeHtml(item.id)}"
    data-dsp-assignment="${escapeHtml(assignmentId)}">${escapeHtml(item.label)}</button>`;
}


export function rowActionsMarkup(row, options = {}) {
  const actions = buildDspRowActions(row, options);
  if (!actions.all.length) return "";
  const assignmentId = String(row.assignment_id || "");
  const secondary = actions.secondary
    .map((item) => actionButton(item, assignmentId)).join("");
  if (!actions.primary) {
    return `<div class="dsp-row-actions dsp-row-actions-discreet">
      <details><summary>Dettagli</summary><div>${secondary}</div></details>
    </div>`;
  }
  return `<div class="dsp-row-actions">
    ${actionButton(actions.primary, assignmentId, true)}
    ${secondary ? `<details><summary>Altre azioni</summary><div>${secondary}</div></details>` : ""}
  </div>`;
}


export function rowMarkup(row, actionOptions = {}) {
  const route = row.route || "Non assegnata";
  const wave = row.wave ? ` · ${row.wave}` : "";
  const tone = rowTone(row);
  const clear = tone === "clear";
  const workforceState = row.workforce?.convocable === false
    ? "unavailable"
    : row.workforce?.availability_status;
  const fleetState = row.fleet?.operational_status || row.fleet?.availability;
  const rowLabel = [
    driverLabel(row), vehicleLabel(row),
    clear ? "Situazione regolare" : `${row.signals.length} criticità`,
  ].join(" · ");
  return `
    <article class="dsp-board-row ${clear ? "is-clear" : `has-attention tone-${escapeHtml(tone)}`}"
      aria-label="${escapeHtml(rowLabel)}">
      <div class="dsp-primary dsp-driver">
        <span class="dsp-mobile-label">Driver</span>
        <strong>${escapeHtml(driverLabel(row))}</strong>
        ${row.workforce?.contract ? `<small>${escapeHtml(row.workforce.contract)}</small>` : ""}
      </div>
      <div class="dsp-primary dsp-vehicle">
        <span class="dsp-mobile-label">Mezzo</span>
        <strong>${escapeHtml(vehicleLabel(row))}</strong>
        ${row.vehicle?.model ? `<small>${escapeHtml(row.vehicle.model)}</small>` : ""}
      </div>
      <div class="dsp-attention">
        <span class="dsp-mobile-label">Criticità</span>
        <div>${signalMarkup(row.signals)}</div>
      </div>
      <div class="dsp-source-state">
        <span class="dsp-mobile-label">Workforce</span>
        <strong>${escapeHtml(statusLabel(workforceState))}</strong>
        ${!clear && row.workforce?.reason ? `<small>${escapeHtml(row.workforce.reason)}</small>` : ""}
        ${!clear && row.workforce?.consecutivity_indicator ? `<small>Consecutività: ${escapeHtml(row.workforce.consecutivity_indicator)}</small>` : ""}
      </div>
      <div class="dsp-source-state">
        <span class="dsp-mobile-label">Fleet</span>
        <strong>${escapeHtml(statusLabel(fleetState))}</strong>
        ${!clear && row.fleet?.availability && row.fleet.availability !== fleetState
          ? `<small>${escapeHtml(statusLabel(row.fleet.availability))}</small>` : ""}
      </div>
      <div class="dsp-source-state dsp-journal-state">
        <span class="dsp-mobile-label">Journal</span>
        ${journalMarkup(row.journal, clear)}
      </div>
      <div class="dsp-source-state dsp-damage-state">
        <span class="dsp-mobile-label">Danni</span>
        ${damageMarkup(row.damage, clear)}
      </div>
      <div class="dsp-route">
        <span class="dsp-mobile-label">Route / wave</span>
        <strong>${escapeHtml(route)}${escapeHtml(wave)}</strong>
      </div>
      ${clear ? `
        <div class="dsp-normal-overview">
          <span>Situazione regolare</span>
          <small>${escapeHtml(statusLabel(workforceState))} · ${escapeHtml(statusLabel(fleetState))} · ${escapeHtml(procedureLabel("check_out", row.journal?.check_out_status))}</small>
        </div>
      ` : ""}
      ${rowActionsMarkup(row, actionOptions)}
    </article>
  `;
}


export function partialMessages(sources = {}) {
  return partialSourceItems(sources).map((item) => item.message);
}


function renderWarnings(refs, sources) {
  const items = partialSourceItems(sources);
  refs.warnings.hidden = !items.length;
  if (!items.length) {
    refs.warnings.replaceChildren();
    return;
  }
  refs.warnings.innerHTML = `
    <details>
      <summary>
        <span>Alcune fonti dati sono parzialmente disponibili</span>
        <span class="dsp-source-count">${items.length}</span>
      </summary>
      <ul>${items.map((item) => (
        `<li><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.message)}</span></li>`
      )).join("")}</ul>
    </details>
  `;
}


function valueOrDash(value) {
  return value == null ? "—" : String(value);
}


function coverageLabel(item) {
  if (item.cycle === "NEXT_DAY") return "Next Day";
  return item.segment === "A" ? "Same Day A" : "Same Day B-C";
}


export function coverageMarkup(items = []) {
  if (!items.length) {
    return '<p class="dsp-coverage-empty">Nessun dato Coverage per la giornata.</p>';
  }
  return items.map((item) => {
    const gap = item.requirement_gap;
    const reserve = item.reserve;
    const balance = gap > 0
      ? `<strong class="is-gap">Mancano ${escapeHtml(gap)}</strong>`
      : reserve > 0
        ? `<strong class="is-reserve">+${escapeHtml(reserve)} scorte</strong>`
        : '<strong class="is-balanced">Copertura allineata</strong>';
    return `
      <article class="dsp-coverage-card" data-coverage-status="${escapeHtml(item.status)}">
        <header><h4>${escapeHtml(coverageLabel(item))}</h4><span>${escapeHtml(COVERAGE_STATUS_LABELS[item.status] || "Da verificare")}</span></header>
        <dl>
          <div><dt>Forecast</dt><dd>${escapeHtml(valueOrDash(item.forecast))}</dd></div>
          <div><dt>Requisito</dt><dd>${escapeHtml(valueOrDash(item.requirement))}</dd></div>
          <div><dt>Assegnati</dt><dd>${escapeHtml(valueOrDash(item.assigned))}</dd></div>
        </dl>
        <p>${balance}</p>
      </article>
    `;
  }).join("");
}


function renderOperationalWarnings(refs, warnings = []) {
  refs.operationalWarnings.hidden = !warnings.length;
  refs.operationalWarnings.innerHTML = warnings.length
    ? `<details><summary>${warnings.length} attenzioni operative</summary><ul>${warnings.map((item) => (
      `<li class="tone-${escapeHtml(item.severity)}">${escapeHtml(item.message)}</li>`
    )).join("")}</ul></details>`
    : "";
}


function renderFilterState(view) {
  document.querySelectorAll("[data-dsp-filter]").forEach((button) => {
    const active = button.dataset.dspFilter === view.filter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}


export function renderDspWorkspace(refs, view) {
  refs.date.value = view.operationDate;
  if (view.phase === "loading") {
    refs.data.hidden = true;
    renderViewState(refs.state, {
      state: "loading",
      title: "Caricamento DSP Workspace",
    });
    return;
  }
  if (view.phase === "error") {
    refs.data.hidden = true;
    renderViewState(refs.state, {
      state: "error",
      title: view.message,
      description: "La navigazione resta disponibile.",
      actionLabel: "Riprova",
      action: "dsp-retry",
    });
    return;
  }

  refs.data.hidden = false;
  refs.sourceLabel.textContent = SOURCE_LABELS[view.sourceType] || "Dati non disponibili";
  refs.summaryDrivers.textContent = String(view.summary.drivers);
  refs.summaryAvailable.textContent = valueOrDash(view.summary.available);
  refs.summaryAbsences.textContent = valueOrDash(view.summary.absences);
  refs.summaryAttention.textContent = String(view.summary.attention);
  refs.summaryAttention.parentElement?.classList.toggle(
    "is-active", view.summary.attention > 0,
  );
  refs.search.value = view.search;
  refs.sort.value = view.sort;
  refs.resultCount.textContent = `${view.rows.length} di ${view.totalRows} assegnazioni`;
  refs.coverage.innerHTML = coverageMarkup(view.coverage);
  renderOperationalWarnings(refs, view.warnings);
  renderWarnings(refs, view.sources);
  renderFilterState(view);

  if (!view.hasOperationalData) {
    refs.board.hidden = true;
    renderViewState(refs.state, {
      state: "empty",
      title: "Nessun dato operativo disponibile per questa giornata.",
      description: "Non risultano Planning, assegnazioni Workforce o Coverage.",
    });
    return;
  }
  if (!view.totalRows) {
    refs.board.hidden = true;
    renderViewState(refs.state, {
      state: "empty",
      title: view.sourceType === "WORKFORCE_OPERATIONAL_PROJECTION"
        ? "Pianificazione Workforce disponibile."
        : "Nessuna assegnazione disponibile.",
      description: view.coverage.length
        ? "Il Coverage della giornata e disponibile; non risultano driver assegnati."
        : "La fonte operativa non contiene righe driver.",
    });
    return;
  }

  refs.state.hidden = true;
  refs.board.hidden = false;
  refs.rows.innerHTML = view.rows.length
    ? view.rows.map(rowMarkup).join("")
    : '<div class="dsp-filter-empty">Nessun risultato per i filtri selezionati.</div>';
}


export function dspWorkspaceRefs() {
  return {
    date: byId("dspOperationDate"),
    today: byId("dspTodayButton"),
    state: byId("dspViewState"),
    data: byId("dspWorkspaceData"),
    warnings: byId("dspSourceWarnings"),
    operationalWarnings: byId("dspOperationalWarnings"),
    sourceLabel: byId("dspSourceLabel"),
    openWorkforce: byId("dspOpenWorkforcePlanning"),
    summaryDrivers: byId("dspSummaryDrivers"),
    summaryAvailable: byId("dspSummaryAvailable"),
    summaryAbsences: byId("dspSummaryAbsences"),
    summaryAttention: byId("dspSummaryAttention"),
    coverage: byId("dspCoverageBuckets"),
    search: byId("dspSearch"),
    sort: byId("dspSort"),
    resultCount: byId("dspResultCount"),
    board: byId("dspBoard"),
    rows: byId("dspBoardRows"),
  };
}

import { byId, escapeHtml, renderViewState } from "../../utils/dom.js";


const SIGNAL_LABELS = Object.freeze({
  DRIVER_WITHOUT_VEHICLE: "Mezzo non assegnato",
  DRIVER_NOT_AVAILABLE: "Driver non disponibile",
  VEHICLE_NOT_AVAILABLE: "Mezzo non disponibile",
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
  if (!signals.length) return '<span class="dsp-clear-label">Nessuna criticità</span>';
  return signals.map((signal) => `
    <span class="dsp-signal dsp-signal-${escapeHtml(signal.severity)}">
      ${escapeHtml(signalLabel(signal.code))}
    </span>
  `).join("");
}


export function rowMarkup(row) {
  const route = row.route || "Non assegnata";
  const wave = row.wave ? ` · ${row.wave}` : "";
  const workforceState = row.workforce?.convocable === false
    ? "unavailable"
    : row.workforce?.availability_status;
  const fleetState = row.fleet?.operational_status || row.fleet?.availability;
  return `
    <article class="dsp-board-row${row.signals.length ? " has-attention" : ""}">
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
        <span class="dsp-mobile-label">Attenzione</span>
        <div>${signalMarkup(row.signals)}</div>
      </div>
      <div class="dsp-route">
        <span class="dsp-mobile-label">Route</span>
        <strong>${escapeHtml(route)}${escapeHtml(wave)}</strong>
      </div>
      <div class="dsp-source-state">
        <span class="dsp-mobile-label">Workforce</span>
        <strong>${escapeHtml(statusLabel(workforceState))}</strong>
        ${row.workforce?.reason ? `<small>${escapeHtml(row.workforce.reason)}</small>` : ""}
        ${row.workforce?.consecutivity_indicator ? `<small>Consecutività: ${escapeHtml(row.workforce.consecutivity_indicator)}</small>` : ""}
      </div>
      <div class="dsp-source-state">
        <span class="dsp-mobile-label">Fleet</span>
        <strong>${escapeHtml(statusLabel(fleetState))}</strong>
        ${row.fleet?.availability && row.fleet.availability !== fleetState
          ? `<small>${escapeHtml(statusLabel(row.fleet.availability))}</small>` : ""}
      </div>
    </article>
  `;
}


export function partialMessages(sources = {}) {
  return Object.entries(sources).flatMap(([source, metadata]) => {
    const label = { planning: "Planning", workforce: "Workforce", fleet: "Fleet" }[source] || source;
    if (!metadata?.available) return [`Stato ${label} temporaneamente non disponibile.`];
    if (metadata.partial) return [`Dati ${label} parzialmente disponibili.`];
    return [];
  });
}


function renderWarnings(refs, sources) {
  const messages = partialMessages(sources);
  refs.warnings.hidden = !messages.length;
  refs.warnings.innerHTML = messages.map((message) => (
    `<p>${escapeHtml(message)}</p>`
  )).join("");
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
  refs.summaryDrivers.textContent = String(view.summary.drivers);
  refs.summaryVehicles.textContent = String(view.summary.vehicles);
  refs.summaryAttention.textContent = String(view.summary.attention);
  refs.search.value = view.search;
  refs.sort.value = view.sort;
  refs.resultCount.textContent = `${view.rows.length} di ${view.totalRows} assegnazioni`;
  renderWarnings(refs, view.sources);
  renderFilterState(view);

  if (!view.planningAvailable) {
    refs.board.hidden = true;
    renderViewState(refs.state, {
      state: "empty",
      title: "Nessun Planning pubblicato o confermato per questa giornata.",
      description: "Seleziona un'altra data operativa.",
    });
    return;
  }
  if (!view.totalRows) {
    refs.board.hidden = true;
    renderViewState(refs.state, {
      state: "empty",
      title: "Nessuna assegnazione disponibile.",
      description: "Il Planning non contiene righe operative.",
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
    summaryDrivers: byId("dspSummaryDrivers"),
    summaryVehicles: byId("dspSummaryVehicles"),
    summaryAttention: byId("dspSummaryAttention"),
    search: byId("dspSearch"),
    sort: byId("dspSort"),
    resultCount: byId("dspResultCount"),
    board: byId("dspBoard"),
    rows: byId("dspBoardRows"),
  };
}

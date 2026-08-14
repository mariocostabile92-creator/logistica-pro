const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function parseOperationalDate(value) {
  if (!DATE_PATTERN.test(String(value || ""))) return null;
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function toOperationalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayOperationalDate(now = new Date()) {
  return toOperationalDate(now);
}

export function addOperationalDays(value, amount) {
  const date = parseOperationalDate(value);
  if (!date) return null;
  date.setDate(date.getDate() + amount);
  return toOperationalDate(date);
}

export function operationalWeek(value) {
  const date = parseOperationalDate(value);
  if (!date) return [];
  const mondayOffset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - mondayOffset);
  return Array.from({ length: 7 }, (_, index) => {
    const current = new Date(date);
    current.setDate(date.getDate() + index);
    return toOperationalDate(current);
  });
}

export function formatOperationalDay(value, options = {}) {
  const date = parseOperationalDate(value);
  if (!date) return "Data non disponibile";
  return new Intl.DateTimeFormat("it-IT", {
    weekday: options.short ? "short" : "long",
    day: "numeric",
    month: options.short ? undefined : "long",
  }).format(date);
}

export function dayReadiness(payload) {
  if (!payload) return { symbol: "—", label: "Dati non caricati", tone: "missing" };
  if (["confirmed", "published"].includes(payload.lifecycle?.state)) {
    return { symbol: "✓", label: "Giornata confermata", tone: "ready" };
  }
  const coverageAvailable = Boolean(payload.coverage?.available);
  const workforceAvailable = payload.workforce?.summary?.planned != null;
  if (!coverageAvailable && !workforceAvailable && !payload.route_data_available) {
    return { symbol: "—", label: "Dati mancanti", tone: "missing" };
  }
  const covered = payload.coverage?.requirement_covered === true;
  const routesReady = payload.route_data_available
    && Number(payload.summary?.routes_incomplete || 0) === 0;
  const vehiclesReady = payload.vehicle_assignments_available;
  const conflictsClear = Number(payload.summary?.blocking_conflicts || 0) === 0;
  if (covered && routesReady && vehiclesReady && conflictsClear) {
    return { symbol: "✓", label: "Giornata pronta", tone: "ready" };
  }
  return { symbol: "⚠", label: "Preparazione incompleta", tone: "attention" };
}

export function renderDayNavigation(selectedDate, weekPayloads = new Map()) {
  const days = operationalWeek(selectedDate);
  return `<section class="planning-day-navigation" aria-label="Navigazione giornata operativa">
    <header>
      <div><p class="eyebrow">Giornata operativa</p><strong>${formatOperationalDay(selectedDate)}</strong></div>
      <nav aria-label="Cambia giornata">
        <button type="button" class="secondary" data-planning-day-jump="previous" aria-label="Giorno precedente">←</button>
        <button type="button" class="secondary" data-planning-day-jump="today">Oggi</button>
        <button type="button" class="secondary" data-planning-day-jump="next" aria-label="Giorno successivo">→</button>
      </nav>
      <label><span>Vai alla data</span><input type="date" value="${selectedDate}" data-planning-operation-date aria-label="Data operativa"></label>
    </header>
    <div class="planning-week-strip" role="tablist" aria-label="Settimana operativa">
      ${days.map((date) => {
        const readiness = dayReadiness(weekPayloads.get(date));
        const selected = date === selectedDate;
        const parsed = parseOperationalDate(date);
        const weekday = new Intl.DateTimeFormat("it-IT", { weekday: "short" }).format(parsed);
        return `<button type="button" role="tab" data-planning-select-date="${date}" aria-selected="${selected}" ${selected ? 'aria-current="date"' : ""} class="planning-week-day ${selected ? "is-selected" : ""}">
          <span>${weekday}</span><strong>${parsed.getDate()}</strong><small class="is-${readiness.tone}" aria-label="${readiness.label}">${selected ? "● " : ""}${readiness.symbol}</small>
        </button>`;
      }).join("")}
    </div>
  </section>`;
}

function dailyCoverageTotal(payload, key) {
  const items = payload?.coverage?.items || [];
  if (!items.some((item) => item[key] != null)) return null;
  return items.reduce((total, item) => total + Number(item[key] || 0), 0);
}

export function summarizeOperationalWeek(selectedDate, weekPayloads = new Map()) {
  const days = operationalWeek(selectedDate);
  const payloads = days.map((date) => weekPayloads.get(date)).filter(Boolean);
  const complete = payloads.length === days.length;
  return {
    complete,
    loadedDays: payloads.length,
    forecast: complete
      ? payloads.reduce((total, payload) => total + Number(dailyCoverageTotal(payload, "forecast") || 0), 0)
      : null,
    requirement: complete
      ? payloads.reduce((total, payload) => total + Number(dailyCoverageTotal(payload, "requirement") || 0), 0)
      : null,
    coveredDays: complete
      ? payloads.filter((payload) => payload.coverage?.requirement_covered === true).length
      : null,
    incompleteDays: complete
      ? payloads.filter((payload) => dayReadiness(payload).tone === "attention").length
      : null,
  };
}

export function renderWeekSummary(selectedDate, weekPayloads, { loading = false, error = null } = {}) {
  const summary = summarizeOperationalWeek(selectedDate, weekPayloads);
  const body = summary.complete
    ? `<dl><div><dt>Forecast settimana</dt><dd>${summary.forecast}</dd></div><div><dt>Requirement settimana</dt><dd>${summary.requirement}</dd></div><div><dt>Giorni coperti</dt><dd>${summary.coveredDays}</dd></div><div><dt>Giorni incompleti</dt><dd>${summary.incompleteDays}</dd></div></dl>`
    : `<p>${error || (loading ? "Caricamento del riepilogo settimanale…" : `${summary.loadedDays} di 7 giornate caricate.`)}</p>${loading ? "" : '<button type="button" class="secondary" data-load-planning-week>Carica riepilogo settimana</button>'}`;
  return `<details class="planning-week-summary"><summary>Riepilogo settimana <span>Secondario</span></summary><div>${body}</div></details>`;
}

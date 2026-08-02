import { escapeHtml } from "../../utils/dom.js";

export function calendarDaySummary({ date, day, metrics, selectedDate, today }) {
  const selected = date === selectedDate;
  const isToday = date === today;
  const hasData = Boolean(metrics?.total);
  const anomalies = Number(metrics?.anomalies || 0);
  const incomplete = Number(metrics?.incomplete || 0);
  const withMedia = Number(metrics?.with_media || 0);
  const classes = [
    "gdb-calendar-day",
    hasData && "has-events",
    anomalies > 0 && "has-anomalies",
    incomplete > 0 && "has-incomplete",
    selected && "active",
    isToday && "is-today",
  ].filter(Boolean).join(" ");
  const summary = hasData
    ? `${metrics.total} GDB, ${anomalies} anomalie, ${incomplete} incomplete, ${withMedia} con allegati`
    : "nessun GDB";
  const label = `${new Date(`${date}T12:00:00`).toLocaleDateString("it-IT", {
    day: "numeric", month: "long", year: "numeric",
  })}: ${summary}`;
  return `<button type="button" class="${classes}" data-gdb-date="${date}"
    aria-pressed="${selected}" ${isToday ? 'aria-current="date"' : ""}
    aria-label="${escapeHtml(label)}">
    <strong>${day}</strong>${hasData ? `<span class="gdb-day-total">${metrics.total}<small> GDB</small></span>
      <span class="gdb-day-signals">${anomalies ? `<b class="gdb-day-anomalies">${anomalies} anomalie</b>` : ""}
        ${incomplete ? `<b class="gdb-day-incomplete">${incomplete} incomplete</b>` : ""}</span>
      ${withMedia ? `<i class="gdb-media-indicator" aria-label="${withMedia} GDB con allegati">${withMedia} media</i>` : ""}` : '<small class="gdb-day-empty">—</small>'}
  </button>`;
}

export function disabledCalendarDay(position) {
  return `<button type="button" class="gdb-calendar-day is-outside" disabled
    aria-label="Giorno fuori dal mese, posizione ${position}"></button>`;
}

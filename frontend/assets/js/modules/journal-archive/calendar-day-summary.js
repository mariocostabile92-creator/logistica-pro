import { escapeHtml } from "../../utils/dom.js";

export function calendarDensity(total = 0) {
  if (total >= 9) return "high";
  if (total >= 4) return "medium";
  return total > 0 ? "low" : "empty";
}

export function calendarDaySummary({ date, day, metrics, selectedDate, today }) {
  const selected = date === selectedDate;
  const isToday = date === today;
  const total = Number(metrics?.total || 0);
  const hasData = total > 0;
  const anomalies = Number(metrics?.anomalies || 0);
  const incomplete = Number(metrics?.incomplete || 0);
  const complete = Math.max(0, total - incomplete);
  const withMedia = Number(metrics?.with_media || 0);
  const density = calendarDensity(total);
  const classes = [
    "gdb-calendar-day",
    `density-${density}`,
    hasData && "has-events",
    anomalies > 0 && "has-anomalies",
    incomplete > 0 && "has-incomplete",
    selected && "active",
    isToday && "is-today",
  ].filter(Boolean).join(" ");
  const summary = hasData
    ? `${total} GDB, ${complete} complete, ${incomplete} incomplete, ${anomalies} anomalie, ${withMedia} con allegati`
    : "nessun GDB";
  const formattedDate = new Date(`${date}T12:00:00`);
  const label = `${formattedDate.toLocaleDateString("it-IT", {
    day: "numeric", month: "long", year: "numeric",
  })}: ${summary}`;
  const monthLabel = formattedDate.toLocaleDateString("it-IT", { month: "short" })
    .replace(".", "").toUpperCase();
  return `<button type="button" class="${classes}" data-gdb-date="${date}"
    aria-pressed="${selected}" ${isToday ? 'aria-current="date"' : ""}
    aria-label="${escapeHtml(label)}">
    <span class="gdb-day-date"><strong>${day}</strong><small>${monthLabel}</small>${isToday ? '<i>Oggi</i>' : ""}</span>
    ${hasData ? `<span class="gdb-day-volume"><strong>${total}</strong><span>GDB</span><small>${complete} complete</small></span>
      <span class="gdb-day-signals">
        ${anomalies ? `<b class="gdb-day-anomalies"><span aria-hidden="true">!</span>${anomalies} anomalie</b>` : ""}
        ${incomplete ? `<b class="gdb-day-incomplete"><span aria-hidden="true">◐</span>${incomplete} incomplete</b>` : ""}
        ${withMedia ? `<b class="gdb-media-indicator"><span aria-hidden="true">▣</span>${withMedia} media</b>` : ""}
      </span>` : '<span class="gdb-day-empty">—</span>'}
  </button>`;
}

export function disabledCalendarDay(position) {
  return `<button type="button" class="gdb-calendar-day is-outside" disabled
    aria-label="Giorno fuori dal mese, posizione ${position}"></button>`;
}

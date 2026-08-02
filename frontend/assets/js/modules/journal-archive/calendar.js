import { escapeHtml } from "../../utils/dom.js";

export function archiveCalendar(month, selectedDate, days = []) {
  const counts = new Map(days.map(day => [day.date, day]));
  const [year, monthNumber] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, monthNumber - 1, 1));
  const blanks = (first.getUTCDay() + 6) % 7;
  const last = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const cells = Array.from({ length: blanks }, () => `<span class="gdb-calendar-empty" aria-hidden="true"></span>`);
  for (let day = 1; day <= last; day += 1) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    const metrics = counts.get(date);
    const summary = metrics
      ? `${metrics.total} procedure, ${metrics.anomalies} anomalie, ${metrics.incomplete} incomplete, ${metrics.with_media} con media`
      : "Nessuna procedura";
    cells.push(`<button type="button" class="gdb-calendar-day ${date === selectedDate ? "active" : ""} ${metrics ? "has-events" : ""}"
      data-gdb-date="${date}" aria-pressed="${date === selectedDate}" aria-label="${day}: ${escapeHtml(summary)}">
      <strong>${day}</strong>${metrics ? `<span>${metrics.total}</span><small>${metrics.incomplete} incomplete · ${metrics.anomalies} anomalie</small>
        ${metrics.with_media ? '<i class="gdb-media-indicator" aria-label="Media presenti">Media</i>' : ""}` : `<small>—</small>`}
    </button>`);
  }
  return `<div class="gdb-calendar-weekdays" aria-hidden="true">${["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map(label => `<span>${label}</span>`).join("")}</div>
    <div class="gdb-calendar-grid" role="grid">${cells.join("")}</div>`;
}

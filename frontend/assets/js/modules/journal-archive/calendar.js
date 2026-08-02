import {
  calendarDaySummary, disabledCalendarDay,
} from "./calendar-day-summary.js";

export function archiveCalendar(month, selectedDate, days = [], today = null) {
  const counts = new Map(days.map(day => [day.date, day]));
  const [year, monthNumber] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, monthNumber - 1, 1));
  const blanks = (first.getUTCDay() + 6) % 7;
  const last = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const cells = Array.from({ length: blanks }, (_, index) => disabledCalendarDay(index + 1));
  for (let day = 1; day <= last; day += 1) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    cells.push(calendarDaySummary({
      date, day, metrics: counts.get(date), selectedDate, today,
    }));
  }
  while (cells.length < 42) cells.push(disabledCalendarDay(cells.length + 1));
  return `<div class="gdb-calendar-weekdays" aria-hidden="true">${["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map(label => `<span>${label}</span>`).join("")}</div>
    <div class="gdb-calendar-grid" role="grid" aria-label="Calendario mensile GDB">${cells.join("")}</div>`;
}

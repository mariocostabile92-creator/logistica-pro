const MONTHS = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];


function localDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0);
}


export function formatShiftPeriod(startValue, endValue) {
  const start = localDate(startValue);
  const end = localDate(endValue);
  if (start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth())
    return `${start.getDate()}–${end.getDate()} ${MONTHS[end.getMonth()]}`;
  return `${start.getDate()} ${MONTHS[start.getMonth()]} – ${end.getDate()} ${MONTHS[end.getMonth()]}`;
}


function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}


function toneFor(day, shift) {
  if (day.missing) return "missing";
  const label = String(shift.display_label || "").toLocaleLowerCase("it-IT");
  if (["riposo", "ferie", "permesso", "malattia"].includes(label)) return "absence";
  return shift.availability === false ? "neutral" : "scheduled";
}


function renderShift(day, shift) {
  const item = node("div", `driver-shift-entry is-${toneFor(day, shift)}`);
  item.append(node("strong", "driver-shift-code", shift.display_label || "Turno non disponibile"));
  if (shift.start_time || shift.end_time) {
    const time = [shift.start_time, shift.end_time].filter(Boolean).join(" – ");
    item.append(node("span", "driver-shift-time", time));
  }
  if (shift.station) item.append(node("span", "driver-shift-station", shift.station));
  return item;
}


export function renderDriverShiftWeek(root, week) {
  const fragment = document.createDocumentFragment();
  week.days.forEach((day) => {
    const card = node("article", "driver-shift-day");
    card.dataset.missing = day.missing ? "true" : "false";
    const heading = node("h3", "driver-shift-day-title", day.date_label);
    const time = document.createElement("time");
    time.dateTime = day.operational_date;
    time.append(heading);
    card.append(time);
    const entries = node("div", "driver-shift-day-entries");
    day.shifts.forEach((shift) => entries.append(renderShift(day, shift)));
    card.append(entries);
    fragment.append(card);
  });
  root.replaceChildren(fragment);
}

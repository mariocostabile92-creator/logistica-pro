import { escapeHtml } from "../utils/dom.js";


const STATUS_LABELS = Object.freeze({
  scheduled: "Programmato",
  available: "Disponibile",
  available_limited: "Disponibile con limitazioni",
  rest: "Riposo",
  leave: "Ferie",
  sickness: "Malattia",
  permission: "Permesso",
  unavailable: "Non disponibile",
  unknown: "Da verificare",
});


export function workforceWeekCopyValueLabel(value) {
  if (!value) return "Nessun turno da copiare";
  const primary = value.shift_code || STATUS_LABELS[value.status_code] || "Da verificare";
  const time = value.start_time || value.end_time
    ? ` · ${value.start_time || "--"}–${value.end_time || "--"}`
    : "";
  const activity = value.operational_activity ? ` · ${value.operational_activity}` : "";
  return `${primary}${activity}${time}`;
}


export function workforceWeekCopyDayLabel(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "long",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


export function renderWorkforceWeekCopyPreview(container, preview) {
  container.innerHTML = preview.days.map((day) => {
    const sourceLabel = workforceWeekCopyValueLabel(day.source);
    const targetLabel = day.target
      ? `<span>Esistente: <strong>${escapeHtml(workforceWeekCopyValueLabel(day.target))}</strong></span>`
      : `<span>Target libero</span>`;
    const outcome = !day.source
      ? `<b class="is-missing">Nessun turno da copiare</b>`
      : day.will_overwrite
        ? `<b class="is-overwrite">Verrà sostituito</b>`
        : `<b class="is-ready">Pronto per la copia</b>`;
    return `
      <article class="workforce-week-copy-row${day.will_overwrite ? " has-overwrite" : ""}${!day.source ? " is-missing" : ""}">
        <div>
          <strong>${escapeHtml(workforceWeekCopyDayLabel(day.target_date))}</strong>
          <small>${escapeHtml(day.source_date)} → ${escapeHtml(day.target_date)}</small>
        </div>
        <div>
          <span>Da copiare: <strong>${escapeHtml(sourceLabel)}</strong></span>
          ${targetLabel}
        </div>
        ${outcome}
      </article>
    `;
  }).join("");
}


export function workforceWeekCopySummary(preview) {
  return {
    copiedCount: preview.days.filter((day) => Boolean(day.source)).length,
    missingCount: Number(preview.missing_count || 0),
    overwriteCount: Number(preview.overwrite_count || 0),
  };
}

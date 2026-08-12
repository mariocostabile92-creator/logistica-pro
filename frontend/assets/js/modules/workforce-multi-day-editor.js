const STATUS_CHOICES = Object.freeze([
  { value: "status:rest", label: "Riposo" },
  { value: "status:holiday", label: "Ferie" },
  { value: "status:sickness", label: "Malattia" },
  { value: "status:leave", label: "Permesso" },
  { value: "status:available", label: "Disponibile" },
  { value: "status:available_limited", label: "Disponibile con limitazioni" },
  { value: "status:unavailable", label: "Non disponibile" },
  { value: "status:unknown", label: "Da verificare" },
]);


export function workforceBulkChoices(statuses = []) {
  const shiftCodes = [...new Set(
    statuses
      .filter((item) => item.status_code === "scheduled")
      .map((item) => String(item.shift_code || "").trim())
      .filter(Boolean),
  )].sort((left, right) => left.localeCompare(right, "it-IT"));
  return [
    ...shiftCodes.map((code) => ({ value: `shift:${code}`, label: code })),
    ...STATUS_CHOICES,
  ];
}


export function nextMultiDaySelection(
  selectedDates,
  clickedDate,
  visibleDates,
  { shiftKey = false, anchorDate = null } = {},
) {
  const next = new Set(selectedDates);
  if (shiftKey && anchorDate && visibleDates.includes(anchorDate)) {
    const start = visibleDates.indexOf(anchorDate);
    const end = visibleDates.indexOf(clickedDate);
    const [from, to] = start <= end ? [start, end] : [end, start];
    visibleDates.slice(from, to + 1).forEach((date) => next.add(date));
  } else if (next.has(clickedDate)) {
    next.delete(clickedDate);
  } else {
    next.add(clickedDate);
  }
  return { selectedDates: next, anchorDate: clickedDate };
}


function sameDateSelection(selectedDates, targetDates) {
  if (selectedDates.size !== targetDates.length) return false;
  return targetDates.every((date) => selectedDates.has(date));
}


export function workforceQuickSelection(selectedDates, visibleDates, preset) {
  const dates = [...visibleDates].filter(Boolean);
  const targetDates = dates.filter((value) => {
    const weekday = new Date(`${value}T00:00:00Z`).getUTCDay();
    if (preset === "weekdays") return weekday >= 1 && weekday <= 5;
    if (preset === "weekend") return weekday === 0 || weekday === 6;
    return preset === "week";
  });
  return sameDateSelection(selectedDates, targetDates)
    ? new Set()
    : new Set(targetDates);
}


export function workforceQuickSelectionActive(selectedDates, visibleDates, preset) {
  const quickSelection = workforceQuickSelection(new Set(), visibleDates, preset);
  return sameDateSelection(selectedDates, [...quickSelection]);
}


export function workforceBulkPayload(workforceMemberId, dates, choice) {
  const [kind, rawValue = ""] = String(choice || "").split(":", 2);
  const value = rawValue.trim();
  const selectedDates = dates ? [...dates] : [];
  if (!Number.isInteger(Number(workforceMemberId)) || Number(workforceMemberId) <= 0) return null;
  if (!selectedDates.length || !value || !["shift", "status"].includes(kind)) return null;
  return {
    workforce_member_id: Number(workforceMemberId),
    dates: selectedDates.sort(),
    status_code: kind === "shift" ? "scheduled" : value,
    shift_code: kind === "shift" ? value : null,
    source_reference: "manual_bulk",
  };
}


export function workforceNavigationDays(mode, direction) {
  const normalizedDirection = Number(direction) < 0 ? -1 : 1;
  return mode === "day" ? normalizedDirection : normalizedDirection * 7;
}


export function populateWorkforceBulkChoices(select, statuses, currentValue = "") {
  const choices = workforceBulkChoices(statuses);
  select.replaceChildren(new Option("Scegli turno o stato", ""));
  choices.forEach((choice) => select.append(new Option(choice.label, choice.value)));
  select.value = choices.some((choice) => choice.value === currentValue) ? currentValue : "";
}

export const journalArchiveState = {
  month: null,
  selectedDate: null,
  currentOperationalDate: null,
  monthData: null,
  dayData: null,
  selected: null,
  filters: {},
  activeKpi: "",
  loading: false,
};

export function moveMonth(offset) {
  if (!journalArchiveState.month) return;
  const [year, month] = journalArchiveState.month.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1 + offset, 1));
  journalArchiveState.month = next.toISOString().slice(0, 7);
  journalArchiveState.selectedDate = null;
}

export function resetToOperationalToday() {
  journalArchiveState.selectedDate = journalArchiveState.currentOperationalDate;
  journalArchiveState.month = journalArchiveState.currentOperationalDate?.slice(0, 7) || null;
}

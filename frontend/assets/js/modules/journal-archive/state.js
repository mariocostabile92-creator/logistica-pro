const today = () => new Date().toISOString().slice(0, 10);

export const journalArchiveState = {
  month: today().slice(0, 7),
  selectedDate: today(),
  monthData: null,
  dayData: null,
  selected: null,
  filters: {},
  loading: false,
};

export function moveMonth(offset) {
  const [year, month] = journalArchiveState.month.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1 + offset, 1));
  journalArchiveState.month = next.toISOString().slice(0, 7);
}

export function resetToToday() {
  journalArchiveState.selectedDate = today();
  journalArchiveState.month = today().slice(0, 7);
}

const FILTERS = new Set(["all", "attention", "clear"]);
const SORTS = new Set(["default", "driver", "route", "attention"]);


export function localToday(now = new Date()) {
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


export function createDspWorkspaceState({ operationDate = localToday() } = {}) {
  return {
    operationDate,
    loading: true,
    snapshot: null,
    error: null,
    filter: "all",
    search: "",
    sort: "default",
  };
}


export function applyDspWorkspaceEvent(state, event) {
  if (event.type === "date-changed") {
    return { ...state, operationDate: event.operationDate, error: null };
  }
  if (event.type === "load-started") {
    return { ...state, loading: true, error: null };
  }
  if (event.type === "load-completed") {
    return { ...state, loading: false, snapshot: event.snapshot, error: null };
  }
  if (event.type === "load-failed") {
    return { ...state, loading: false, snapshot: null, error: event.error };
  }
  if (event.type === "filter-changed" && FILTERS.has(event.filter)) {
    return { ...state, filter: event.filter };
  }
  if (event.type === "search-changed") {
    return { ...state, search: String(event.search || "") };
  }
  if (event.type === "sort-changed" && SORTS.has(event.sort)) {
    return { ...state, sort: event.sort };
  }
  return state;
}


function signalsByAssignment(signals = []) {
  const grouped = new Map();
  signals.forEach((signal) => {
    const current = grouped.get(signal.assignment_id) || [];
    current.push(signal);
    grouped.set(signal.assignment_id, current);
  });
  return grouped;
}


function rowSearchText(row) {
  return [
    row.driver?.name,
    row.driver?.planning_identifier,
    row.vehicle?.plate,
    row.route,
  ].filter(Boolean).join(" ").toLocaleLowerCase("it");
}


function sortedRows(rows, sort) {
  if (sort === "default") return rows;
  const key = (item) => {
    if (sort === "driver") {
      return item.driver?.name || item.driver?.planning_identifier || "";
    }
    if (sort === "route") return item.route || "";
    return String(999 - item.signals.length).padStart(3, "0");
  };
  return rows
    .map((item, index) => ({ item, index }))
    .sort((left, right) => (
      key(left.item).localeCompare(key(right.item), "it", { numeric: true })
      || left.index - right.index
    ))
    .map(({ item }) => item);
}


export function deriveDspWorkspaceView(state) {
  if (state.loading) return { phase: "loading", operationDate: state.operationDate };
  if (state.error) return {
    phase: "error",
    operationDate: state.operationDate,
    message: "Impossibile caricare il DSP Workspace.",
  };

  const snapshot = state.snapshot || {
    planning: { available: false }, rows: [], signals: [], sources: {},
  };
  const groupedSignals = signalsByAssignment(snapshot.signals);
  const enrichedRows = snapshot.rows.map((row) => ({
    ...row,
    operation_date: snapshot.operation_date || state.operationDate,
    signals: groupedSignals.get(row.assignment_id) || [],
  }));
  const search = state.search.trim().toLocaleLowerCase("it");
  const filteredRows = enrichedRows.filter((row) => {
    if (state.filter === "attention" && !row.signals.length) return false;
    if (state.filter === "clear" && row.signals.length) return false;
    return !search || rowSearchText(row).includes(search);
  });

  return {
    phase: "ready",
    operationDate: state.operationDate,
    planningAvailable: Boolean(snapshot.planning?.available),
    summary: {
      drivers: enrichedRows.filter((row) => (
        row.driver?.name || row.driver?.planning_identifier
      )).length,
      vehicles: enrichedRows.filter((row) => (
        row.vehicle?.fleet_asset_id || row.vehicle?.plate
      )).length,
      attention: snapshot.signals.length,
    },
    sources: snapshot.sources || {},
    totalRows: enrichedRows.length,
    rows: sortedRows(filteredRows, state.sort),
    filter: state.filter,
    search: state.search,
    sort: state.sort,
  };
}

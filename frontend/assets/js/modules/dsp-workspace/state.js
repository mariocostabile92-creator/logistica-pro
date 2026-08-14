import {
  compareAttentionRows,
  orderedSignals,
} from "./presentation.js";


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
  return rows
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      if (sort === "attention") {
        return compareAttentionRows(left.item, right.item) || left.index - right.index;
      }
      const leftKey = sort === "driver"
        ? left.item.driver?.name || left.item.driver?.planning_identifier || ""
        : left.item.route || "";
      const rightKey = sort === "driver"
        ? right.item.driver?.name || right.item.driver?.planning_identifier || ""
        : right.item.route || "";
      return leftKey.localeCompare(rightKey, "it", { numeric: true })
        || left.index - right.index;
    })
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
    signals: orderedSignals(groupedSignals.get(row.assignment_id) || []),
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
    hasOperationalData: Boolean(snapshot.source_type || snapshot.planning?.available),
    sourceType: snapshot.source_type || (
      snapshot.planning?.available ? "LEGACY_OPERATIONAL_PLANNING" : null
    ),
    planningStatus: snapshot.planning_status || snapshot.planning?.status || "no_data",
    summary: {
      drivers: snapshot.counts?.driver_planned_count ?? enrichedRows.filter((row) => (
        row.driver?.name || row.driver?.planning_identifier
      )).length,
      available: snapshot.counts?.driver_available_count ?? null,
      absences: snapshot.counts?.driver_absent_count ?? null,
      reserves: snapshot.counts?.reserve_count ?? 0,
      vehicles: enrichedRows.filter((row) => (
        row.vehicle?.fleet_asset_id || row.vehicle?.plate
      )).length,
      attention: snapshot.signals.length,
    },
    coverage: snapshot.coverage || [],
    warnings: snapshot.warnings || [],
    sources: snapshot.sources || {},
    totalRows: enrichedRows.length,
    rows: sortedRows(filteredRows, state.sort),
    filter: state.filter,
    search: state.search,
    sort: state.sort,
  };
}

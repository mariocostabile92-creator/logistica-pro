export function createPlanningCoverageState() {
  return {
    coverageLoading: false,
    coverageError: null,
    coverageData: null,
    coverageLastUpdated: null,
    coverageCycleFilter: "all",
    coverageFocusedDate: null,
  };
}


export function startPlanningCoverageLoad(state) {
  return {
    ...state,
    coverageLoading: true,
    coverageError: null,
  };
}


export function completePlanningCoverageLoad(state, coverageData, updatedAt = new Date()) {
  return {
    ...state,
    coverageLoading: false,
    coverageError: null,
    coverageData,
    coverageLastUpdated: updatedAt,
  };
}


export function failPlanningCoverageLoad(state, error) {
  return {
    ...state,
    coverageLoading: false,
    coverageError: error || new Error("Impossibile aggiornare la copertura."),
  };
}

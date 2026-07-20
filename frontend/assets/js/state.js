export const state = {
  planning: {
    imported: false,
    validImport: false,
    rows: [],
  },
  fleet: {
    imported: false,
    rows: [],
  },
  fleetPlugin: {
    assets: [],
    selectedAssetId: null,
  },
  configuration: {
    data: null,
  },
  dashboard: {
    data: null,
  },
  planningOperational: {
    data: null,
    filteredAssignments: [],
    simulation: null,
  },
};
